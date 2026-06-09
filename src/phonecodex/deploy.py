from __future__ import annotations

from pathlib import Path


def patch_cloudflared_config(path: Path, hostname: str, service_url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    rule = f"  - hostname: {hostname}\n    service: {service_url}\n"
    if f"hostname: {hostname}" in existing:
        lines = existing.splitlines()
        output: list[str] = []
        skip_next = False
        for idx, line in enumerate(lines):
            if skip_next:
                output.append(f"    service: {service_url}")
                skip_next = False
                continue
            output.append(line)
            if line.strip() == f"hostname: {hostname}":
                skip_next = idx + 1 < len(lines) and lines[idx + 1].strip().startswith("service:")
        path.write_text("\n".join(output) + "\n", encoding="utf-8")
        return
    if "ingress:" not in existing:
        existing = existing.rstrip() + "\ningress:\n"
    fallback = "  - service: http_status:404"
    if fallback in existing:
        existing = existing.replace(fallback, rule + fallback)
    else:
        existing = existing.rstrip() + "\n" + rule + fallback + "\n"
    path.write_text(existing, encoding="utf-8")


def multi_session_name(prefix: str, number: int) -> str:
    return prefix if number == 1 else f"{prefix}-{number}"


def hostname_for_session(pattern: str, base_hostname: str, number: int) -> str:
    if pattern:
        return pattern.format(n=number)
    if number == 1:
        return base_hostname
    stem, dot, suffix = base_hostname.partition(".")
    if not dot:
        return f"{base_hostname}-{number}"
    return f"{stem}{number}.{suffix}"
