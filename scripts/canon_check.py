# -*- coding: utf-8 -*-
"""Bramka kanonu - kopie humanizer-en i humanizer-pl w tej wtyczce maja byc tym samym,
co skill w hubie (awesome-matematic-skills-en / -pl). humanizer-pt mieszka TUTAJ.

Geneza (05.10.2026): paczki Boutique dryfowaly od hubow przez trzy miesiace, bo poprawka
w jednym miejscu nie docierala do kopii. Ta wtyczka to trzecia kopia - bez bramki
powtorzylaby ten sam blad.

Porownanie z BLOBAMI git w HEAD huba (to widac na GitHubie), CRLF znormalizowane.

Trojstan:
  OK       - kazda kopia rowna HEAD huba
  UWAGI    - kopia rowna kopii roboczej huba, ale hub ma te zmiane NIEZACOMMITOWANA
             (exit 0; zacommituj hub, potem bramka da OK)
  BLOKADA  - kopia rozna od huba (dryf), brak klonu huba, pusta lista plikow (exit 1)

Uzycie:
  python scripts/canon_check.py           # bramka
  python scripts/canon_check.py --sync    # nadpisz kopie plikami z HEAD huba
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROJECTS = ROOT.parent
KOPIE = {
    "humanizer-en": ("awesome-matematic-skills-en", "content-quality/skills/humanizer-en"),
    "humanizer-pl": ("awesome-matematic-skills-pl", "jakosc-tresci/skills/humanizer-pl"),
}


def norm(b):
    return b.replace(b"\r\n", b"\n")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True).stdout


def pliki_head(repo, sciezka):
    out = git(repo, "ls-tree", "-r", "--name-only", "HEAD", "--", sciezka).decode("utf-8")
    wynik = {}
    for nazwa in out.splitlines():
        wzgl = nazwa[len(sciezka) + 1:]
        wynik[wzgl] = norm(git(repo, "show", "HEAD:" + nazwa))
    return wynik


def pliki_dysk(katalog):
    return {
        p.relative_to(katalog).as_posix(): norm(p.read_bytes())
        for p in sorted(katalog.rglob("*")) if p.is_file()
    }


def main():
    sync = "--sync" in sys.argv[1:]
    blokady, uwagi, ok = [], [], []
    for slug, (repo_nazwa, sciezka) in KOPIE.items():
        repo = PROJECTS / repo_nazwa
        kopia = ROOT / "skills" / slug
        if not (repo / ".git").exists():
            blokady.append(f"{slug}: brak klonu huba {repo} - nic nie zmierzono")
            continue
        head = pliki_head(repo, sciezka)
        if not head:
            blokady.append(f"{slug}: pusta lista plikow w HEAD {repo_nazwa}:{sciezka}")
            continue
        if sync:
            for wzgl, tresc in head.items():
                cel = kopia / wzgl
                cel.parent.mkdir(parents=True, exist_ok=True)
                cel.write_bytes(tresc)
            for wzgl in set(pliki_dysk(kopia)) - set(head):
                (kopia / wzgl).unlink()
        moja = pliki_dysk(kopia)
        if moja == head:
            ok.append(f"{slug}: == HEAD {repo_nazwa} ({len(head)} plikow)")
        elif moja == pliki_dysk(repo / sciezka):
            uwagi.append(f"{slug}: == kopia robocza {repo_nazwa}, ale hub ma zmiane NIEZACOMMITOWANA")
        else:
            rozne = sorted(k for k in set(moja) | set(head) if moja.get(k) != head.get(k))
            blokady.append(f"{slug}: DRYF wobec {repo_nazwa} w {', '.join(rozne)} (napraw: --sync albo popraw hub)")

    mianownik = len(KOPIE)
    for linia in ok:
        print("  OK      " + linia)
    for linia in uwagi:
        print("  UWAGI   " + linia)
    for linia in blokady:
        print("  BLOKADA " + linia)
    stan = "BLOKADA" if blokady else ("UWAGI" if uwagi else "OK")
    print(f"canon_check: {stan} - OK {len(ok)}/{mianownik}, UWAGI {len(uwagi)}, BLOKADA {len(blokady)}")
    return 1 if blokady else 0


if __name__ == "__main__":
    sys.exit(main())
