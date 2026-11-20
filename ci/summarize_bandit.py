"""Сохранить краткий отчёт текущего Bandit без фрагментов исходного кода."""

import json
from pathlib import Path


def main() -> None:
    report = json.loads(Path("data/bandit-report.json").read_text())
    short = {key: report[key] for key in ("generated_at", "errors", "results")}
    for finding in short["results"]:
        finding.pop("code", None)
    Path("data/bandit-report-short.json").write_text(
        json.dumps(short, ensure_ascii=False, indent=2) + "\n"
    )
    if short["errors"]:
        raise SystemExit("Bandit сообщил об ошибках сканирования; проверка не пройдена")


if __name__ == "__main__":
    main()
