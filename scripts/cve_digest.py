from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

JST = timezone(timedelta(hours=9), "JST")
UTC = timezone.utc
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config" / "cve-digest.json"
HISTORY_PATH = ROOT_DIR / "data" / "cve-history.json"
OUTPUT_ROOT = ROOT_DIR / "docs" / "cve-digest"
USER_AGENT = "cve-digest/1.0"


@dataclass(frozen=True)
class Vulnerability:
    cve_id: str
    title: str
    description: str
    source: str
    published_at: str | None
    updated_at: str | None
    cvss: float | None
    severity: str
    kev: bool
    affected_products: list[str]
    matched_keywords: list[str]
    references: list[str]
    score: int


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")


def fetch_json(url: str, params: dict[str, str] | None = None, timeout: int = 30) -> dict[str, Any]:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(JST)


def format_datetime(value: str | None) -> str | None:
    parsed = parse_datetime(value)
    if parsed is None:
        return value
    return parsed.strftime("%Y-%m-%d %H:%M:%S JST")


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").split())


def get_english_description(descriptions: list[dict[str, Any]]) -> str:
    for description in descriptions:
        if str(description.get("lang", "")).lower() == "en":
            return normalize_text(str(description.get("value", "")))
    if descriptions:
        return normalize_text(str(descriptions[0].get("value", "")))
    return ""


def extract_cvss(cve: dict[str, Any]) -> tuple[float | None, str]:
    metrics = cve.get("metrics", {})
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        values = metrics.get(key) or []
        if not values:
            continue
        metric = values[0]
        data = metric.get("cvssData", {})
        score = data.get("baseScore")
        severity = metric.get("baseSeverity") or data.get("baseSeverity") or "UNKNOWN"
        try:
            return float(score), str(severity).upper()
        except (TypeError, ValueError):
            return None, str(severity).upper()
    return None, "UNKNOWN"


def extract_affected_products(cve: dict[str, Any]) -> list[str]:
    products: set[str] = set()
    configurations = cve.get("configurations") or []
    for configuration in configurations:
        for node in configuration.get("nodes", []) or []:
            for match in node.get("cpeMatch", []) or []:
                criteria = str(match.get("criteria", ""))
                parts = criteria.split(":")
                if len(parts) >= 5:
                    vendor = parts[3].replace("_", " ")
                    product = parts[4].replace("_", " ")
                    if product and product != "*":
                        products.add(f"{vendor} {product}".strip())
    return sorted(products)[:8]


def extract_references(cve: dict[str, Any]) -> list[str]:
    refs = []
    for ref in cve.get("references", {}).get("referenceData", []) or []:
        url = str(ref.get("url", "")).strip()
        if url:
            refs.append(url)
    return refs[:5]


def match_keywords(text: str, keywords: list[str], exclude_keywords: list[str]) -> list[str]:
    lower_text = text.lower()
    if any(keyword.lower() in lower_text for keyword in exclude_keywords):
        return []
    return [keyword for keyword in keywords if keyword.lower() in lower_text]


def calculate_score(cvss: float | None, kev: bool, matched_keywords: list[str], description: str) -> int:
    score = 0
    if kev:
        score += 100
    if cvss is not None:
        if cvss >= 9.0:
            score += 50
        elif cvss >= 7.0:
            score += 30
        elif cvss >= 4.0:
            score += 10
    score += len(matched_keywords) * 10
    lowered = description.lower()
    high_risk_terms = [
        "remote code execution",
        "arbitrary code execution",
        "authentication bypass",
        "privilege escalation",
        "sql injection",
        "cross-site scripting",
    ]
    score += sum(20 for term in high_risk_terms if term in lowered)
    return score


def severity_bucket(vuln: Vulnerability) -> str:
    if vuln.kev:
        return "緊急対応候補"
    if vuln.cvss is not None and vuln.cvss >= 9.0:
        return "Critical"
    if vuln.cvss is not None and vuln.cvss >= 7.0:
        return "High"
    return "Watch"


def fetch_cisa_kev(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    source_config = config.get("sources", {}).get("cisa_kev", {})
    if not source_config.get("enabled", True):
        return {}
    data = fetch_json(str(source_config["url"]))
    kev_items: dict[str, dict[str, Any]] = {}
    for item in data.get("vulnerabilities", []) or []:
        cve_id = str(item.get("cveID", "")).strip()
        if cve_id:
            kev_items[cve_id] = item
    return kev_items


def fetch_nvd_items(config: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    source_config = config.get("sources", {}).get("nvd", {})
    if not source_config.get("enabled", True):
        return []
    lookback_days = int(config.get("lookback_days", 2))
    start = now.astimezone(UTC) - timedelta(days=lookback_days)
    params = {
        "pubStartDate": iso_utc(start),
        "pubEndDate": iso_utc(now),
    }
    data = fetch_json(str(source_config["url"]), params=params, timeout=45)
    return list(data.get("vulnerabilities", []) or [])


def normalize_nvd_item(
    item: dict[str, Any],
    kev_items: dict[str, dict[str, Any]],
    config: dict[str, Any],
) -> Vulnerability | None:
    cve = item.get("cve", {})
    cve_id = str(cve.get("id", "")).strip()
    if not cve_id:
        return None

    description = get_english_description(cve.get("descriptions", []) or [])
    affected_products = extract_affected_products(cve)
    references = extract_references(cve)
    cvss, severity = extract_cvss(cve)
    kev = cve_id in kev_items
    kev_item = kev_items.get(cve_id, {})
    title = normalize_text(str(kev_item.get("vulnerabilityName") or cve_id))
    if title == cve_id and description:
        title = description[:100] + ("..." if len(description) > 100 else "")

    watch_keywords = [str(item) for item in config.get("watch_keywords", [])]
    exclude_keywords = [str(item) for item in config.get("exclude_keywords", [])]
    keyword_text = " ".join([title, description, " ".join(affected_products)])
    matched_keywords = match_keywords(keyword_text, watch_keywords, exclude_keywords)

    min_cvss = float(config.get("min_cvss", 7.0))
    if not kev and not matched_keywords:
        return None
    if not kev and cvss is not None and cvss < min_cvss and not matched_keywords:
        return None

    score = calculate_score(cvss, kev, matched_keywords, description)
    return Vulnerability(
        cve_id=cve_id,
        title=title,
        description=description,
        source="NVD" + (" / CISA KEV" if kev else ""),
        published_at=format_datetime(cve.get("published")),
        updated_at=format_datetime(cve.get("lastModified")),
        cvss=cvss,
        severity=severity,
        kev=kev,
        affected_products=affected_products,
        matched_keywords=matched_keywords,
        references=references,
        score=score,
    )


def prune_history(history: dict[str, Any], now: datetime, retention_days: int) -> dict[str, Any]:
    seen = history.get("seen", {})
    if not isinstance(seen, dict):
        seen = {}
    threshold = (now - timedelta(days=retention_days)).date()
    pruned: dict[str, Any] = {}
    for cve_id, value in seen.items():
        first_seen = str(value.get("first_seen", "")) if isinstance(value, dict) else ""
        try:
            first_seen_date = datetime.strptime(first_seen, "%Y-%m-%d").date()
        except ValueError:
            continue
        if first_seen_date >= threshold:
            pruned[cve_id] = value
    return {"seen": pruned}


def filter_new(vulnerabilities: list[Vulnerability], history: dict[str, Any]) -> list[Vulnerability]:
    seen = history.get("seen", {})
    return [vuln for vuln in vulnerabilities if vuln.cve_id not in seen]


def update_history(history: dict[str, Any], vulnerabilities: list[Vulnerability], now: datetime) -> dict[str, Any]:
    seen = history.setdefault("seen", {})
    today = now.strftime("%Y-%m-%d")
    for vuln in vulnerabilities:
        seen[vuln.cve_id] = {
            "title": vuln.title,
            "severity": vuln.severity,
            "cvss": vuln.cvss,
            "kev": vuln.kev,
            "first_seen": today,
        }
    return history


def render_summary(vulnerabilities: list[Vulnerability], now: datetime, errors: list[str]) -> str:
    date_text = now.strftime("%Y-%m-%d")
    fetched_text = now.strftime("%Y-%m-%d %H:%M:%S JST")
    lines = [
        f"# CVE Digest ({date_text})",
        "",
        f"- 取得日時: {fetched_text}",
        f"- 新規検出数: {len(vulnerabilities)}",
        "- 出力方針: 関心技術に関連するCVE、CVSS 7.0以上、またはCISA KEV掲載を優先",
        "",
    ]

    if errors:
        lines.extend(["## 取得エラー", ""])
        for error in errors:
            lines.append(f"- {error}")
        lines.append("")

    if not vulnerabilities:
        lines.extend(["条件に一致する新規脆弱性はありませんでした。", ""])
        return "\n".join(lines)

    for bucket in ("緊急対応候補", "Critical", "High", "Watch"):
        bucket_items = [vuln for vuln in vulnerabilities if severity_bucket(vuln) == bucket]
        if not bucket_items:
            continue
        lines.extend([f"## {bucket}", ""])
        for vuln in bucket_items:
            products = ", ".join(vuln.affected_products) or "-"
            keywords = ", ".join(vuln.matched_keywords) or "-"
            references = vuln.references[:3]
            lines.extend(
                [
                    f"### {vuln.cve_id}: {vuln.title}",
                    "",
                    f"- 重要度: {vuln.severity}",
                    f"- CVSS: {vuln.cvss if vuln.cvss is not None else '-'}",
                    f"- KEV掲載: {'yes' if vuln.kev else 'no'}",
                    f"- 関連キーワード: {keywords}",
                    f"- 影響製品候補: {products}",
                    f"- 公開日時: {vuln.published_at or '-'}",
                    f"- 更新日時: {vuln.updated_at or '-'}",
                    f"- 概要: {vuln.description or '-'}",
                ]
            )
            if references:
                lines.append("- 参考:")
                for url in references:
                    lines.append(f"  - {url}")
            lines.append("")
    return "\n".join(lines)


def write_summary(markdown: str, now: datetime) -> Path:
    output_dir = OUTPUT_ROOT / now.strftime("%Y-%m-%d")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "summary.md"
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def main() -> int:
    now = datetime.now(JST)
    config = load_json(CONFIG_PATH, {})
    history = load_json(HISTORY_PATH, {"seen": {}})
    history = prune_history(history, now, int(config.get("history_retention_days", 120)))
    errors: list[str] = []

    try:
        kev_items = fetch_cisa_kev(config)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as error:
        kev_items = {}
        errors.append(f"CISA KEV: {error}")

    try:
        nvd_items = fetch_nvd_items(config, now)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as error:
        nvd_items = []
        errors.append(f"NVD: {error}")

    vulnerabilities: list[Vulnerability] = []
    for item in nvd_items:
        vulnerability = normalize_nvd_item(item, kev_items, config)
        if vulnerability is not None:
            vulnerabilities.append(vulnerability)

    vulnerabilities.sort(key=lambda item: item.score, reverse=True)
    max_items = int(config.get("max_items", 30))
    new_vulnerabilities = filter_new(vulnerabilities, history)[:max_items]

    summary = render_summary(new_vulnerabilities, now, errors)
    output_path = write_summary(summary, now)
    print(f"created: {output_path.relative_to(ROOT_DIR)}")

    history = update_history(history, new_vulnerabilities, now)
    write_json(HISTORY_PATH, history)

    if errors:
        print("warning: one or more vulnerability sources failed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
