"""
Move a list of stories to a target PI sprint.

Usage:
    python move_to_pi.py --stories STRY001 STRY002 --pi "16. 5"
    python move_to_pi.py --stories STRY001 STRY002 --pi "16. 5" --team "My Agile Team"
    python move_to_pi.py --stories STRY001 STRY002 --pi "16. 5" --dry-run

Notes:
    - PI label must use the ServiceNow space format: "16. 5" not "16.5"
    - Team is inferred from the first story's current sprint if not specified
    - Duplicate story numbers are silently deduplicated
    - Use --dry-run to preview changes before writing
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from snow_client import SnowClient


def _dv(field) -> str:
    if isinstance(field, dict):
        return field.get("display_value") or field.get("value") or ""
    return str(field) if field else ""


def _val(field) -> str:
    if isinstance(field, dict):
        return field.get("value") or field.get("display_value") or ""
    return str(field) if field else ""


def lookup_stories(client: SnowClient, numbers: list[str]) -> list[dict]:
    query = "numberIN" + ",".join(numbers)
    return client.get_table(
        "rm_story",
        query=query,
        fields=["sys_id", "number", "short_description", "state", "sprint"],
        limit=len(numbers) + 10,
        display_value=True,
    )


def find_pi_sprints(client: SnowClient, pi: str, team: str | None = None) -> list[dict]:
    query = f"short_descriptionLIKE{pi}"
    if team:
        query = f"short_descriptionLIKE{team} - {pi}"
    return client.get_table(
        "rm_sprint",
        query=query,
        fields=["sys_id", "short_description", "state"],
        limit=50,
    )


def main():
    parser = argparse.ArgumentParser(description="Move SNOW stories to a PI sprint")
    parser.add_argument("--stories", nargs="+", required=True, help="Story numbers e.g. STRY0032845")
    parser.add_argument("--pi", required=True, help="PI iteration label, e.g. '16. 5'")
    parser.add_argument("--team", default=None, help="Team name filter (optional if stories all on same team)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    args = parser.parse_args()

    # Deduplicate story numbers preserving order
    seen = set()
    story_numbers = []
    for s in args.stories:
        if s not in seen:
            seen.add(s)
            story_numbers.append(s)

    client = SnowClient()
    print(f"Authenticated as: {client.session_full_name} ({client.session_username})\n")

    # 1. Look up the stories
    print(f"Looking up {len(story_numbers)} stories...")
    stories = lookup_stories(client, story_numbers)
    story_map = {_dv(s.get("number")): s for s in stories}

    for num in story_numbers:
        if num not in story_map:
            print(f"  WARNING: {num} not found in SNOW")

    found = [(num, story_map[num]) for num in story_numbers if num in story_map]
    print(f"  Found {len(found)} of {len(story_numbers)} stories\n")

    for num, s in found:
        sprint_name = _dv(s.get("sprint"))
        print(f"  {num}  [{sprint_name or '(no sprint)'}]  {_dv(s.get('short_description'))[:60]}")

    print()

    # 2. Find PI 16.5 sprint(s)
    team = args.team
    if not team and found:
        # Try to infer team from the first story's current sprint
        first_sprint = _dv(found[0][1].get("sprint"))
        if " - " in first_sprint:
            team = first_sprint.rsplit(" - ", 1)[0]
            print(f"Inferred team from first story's sprint: '{team}'")

    print(f"Searching for PI sprint matching '{args.pi}'...")
    sprints = find_pi_sprints(client, args.pi, team)

    if not sprints:
        print(f"  ERROR: No sprint found matching PI '{args.pi}'" + (f" for team '{team}'" if team else ""))
        sys.exit(1)

    if len(sprints) > 1:
        print(f"  Found {len(sprints)} matching sprints:")
        for i, sp in enumerate(sprints):
            print(f"    [{i}] {_dv(sp.get('short_description'))}  [{_dv(sp.get('state'))}]  sys_id={_val(sp.get('sys_id'))}")
        print()
        choice = input("Select sprint index to use: ").strip()
        target_sprint = sprints[int(choice)]
    else:
        target_sprint = sprints[0]

    sprint_sys_id = _val(target_sprint.get("sys_id")) or _dv(target_sprint.get("sys_id"))
    sprint_name = _dv(target_sprint.get("short_description"))
    print(f"\nTarget sprint: {sprint_name}  (sys_id={sprint_sys_id})\n")

    if args.dry_run:
        print("[DRY RUN] Would update the following stories:")
        for num, s in found:
            print(f"  {num}  sprint → {sprint_name}")
        print("\nNo changes made (--dry-run).")
        return

    # 3. Patch each story
    print(f"Moving {len(found)} stories to '{sprint_name}'...\n")
    success, failed = 0, 0
    for num, s in found:
        sys_id = _val(s.get("sys_id")) or _dv(s.get("sys_id"))
        try:
            result = client.patch_record("rm_story", sys_id, {"sprint": sprint_sys_id})
            new_sprint = _dv(result.get("sprint")) if result else "?"
            print(f"  OK  {num}  sprint={new_sprint}")
            success += 1
        except RuntimeError as e:
            print(f"  ERR {num}  {e}")
            failed += 1

    print(f"\nDone: {success} updated, {failed} failed.")


if __name__ == "__main__":
    main()
