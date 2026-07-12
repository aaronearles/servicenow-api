"""
Generate a PI story report for a given team and PI iteration.

Usage:
    python queries/pi_report.py --team "My Agile Team" --pi "10. 1"

Note: PI iteration names have a space before the number ("10. 1", not "10.1").
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from snow_client import SnowClient

STATE_LABELS = {"-5": "Draft", "1": "Open", "2": "In Progress", "3": "Complete", "4": "Accepted"}


def _dv(field) -> str:
    if isinstance(field, dict):
        return field.get("display_value") or field.get("value") or ""
    return str(field) if field else ""


def find_sprint(client: SnowClient, team: str, pi: str) -> list[dict]:
    """Return rm_sprint records matching team + PI iteration."""
    query = f"short_descriptionLIKE{team} - {pi}"
    return client.get_table(
        "rm_sprint",
        query=query,
        fields=["sys_id", "short_description", "state", "start_date", "end_date"],
    )


def fetch_stories(client: SnowClient, team: str, pi: str, state_filter: str = "3") -> list[dict]:
    """Fetch stories for a team PI iteration, filtered by state (default: Complete)."""
    sprint_pattern = f"{team} - {pi}"
    query = f"sprint.short_descriptionLIKE{sprint_pattern}"
    if state_filter:
        query += f"^state={state_filter}"
    return client.get_table(
        "rm_story",
        query=query,
        fields=[
            "number", "short_description", "story_points",
            "assigned_to", "state", "closed_at", "sprint",
        ],
        limit=500,
    )


def print_report(stories: list[dict], team: str, pi: str) -> int:
    print(f"\n{'=' * 70}")
    print(f"  PI Report: {pi} — {team}")
    print(f"  Completed Stories: {len(stories)}")
    print(f"{'=' * 70}\n")

    total_points = 0
    by_assignee: dict[str, list[dict]] = {}

    for s in stories:
        assignee = _dv(s.get("assigned_to")) or "Unassigned"
        pts_raw = _dv(s.get("story_points"))
        pts = int(pts_raw) if pts_raw and str(pts_raw).isdigit() else 0
        total_points += pts
        by_assignee.setdefault(assignee, []).append({
            "number": _dv(s.get("number")),
            "title": _dv(s.get("short_description")),
            "points": pts,
            "sprint": _dv(s.get("sprint")),
            "closed": _dv(s.get("closed_at")),
        })

    print(f"Total story points completed: {total_points}\n")
    for assignee, items in sorted(by_assignee.items()):
        member_pts = sum(i["points"] for i in items)
        print(f"  {assignee}  ({len(items)} stories, {member_pts} pts)")
        for i in items:
            pts_str = f"[{i['points']}pt]" if i["points"] else "[?pt]"
            print(f"    {i['number']}  {pts_str}  {i['title'][:60]}")
        print()

    return total_points


def list_sprints(client: SnowClient, team: str):
    """Print all PI sprint iterations for a team."""
    sprints = client.get_table(
        "rm_sprint",
        query=f"short_descriptionLIKE{team}",
        fields=["short_description", "state", "start_date", "end_date"],
        limit=50,
    )
    if not sprints:
        print(f"No sprints found for team: {team}")
        return
    print(f"\n{'Sprint':<55} {'State':<12} {'Start'}")
    print("-" * 85)
    for s in sorted(sprints, key=lambda x: _dv(x.get("short_description"))):
        print(f"  {_dv(s.get('short_description')):<53} {_dv(s.get('state')):<12} {_dv(s.get('start_date'))[:10]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--team", required=True, help="Team name as it appears in sprint short_description")
    parser.add_argument("--pi", default="10. 1",
                        help="PI iteration label suffix, e.g. '10. 1' (note the space)")
    parser.add_argument("--all-states", action="store_true",
                        help="Include all states, not just Complete")
    parser.add_argument("--list", action="store_true",
                        help="List available PI sprints for the team and exit")
    args = parser.parse_args()

    client = SnowClient()
    print(f"Authenticated as: {client.session_full_name} ({client.session_username})")

    if args.list:
        list_sprints(client, args.team)
        return

    print(f"\nLooking up sprint for '{args.team} - {args.pi}'...")
    sprints = find_sprint(client, args.team, args.pi)
    if not sprints:
        print("  No matching sprint found. Try --list to see available PI names.")
        return
    for sp in sprints:
        print(f"  Found: {_dv(sp.get('short_description'))}  [{_dv(sp.get('state'))}]")

    state_filter = "" if args.all_states else "3"
    label = "all" if args.all_states else "completed"
    print(f"\nFetching {label} stories...")
    stories = fetch_stories(client, args.team, args.pi, state_filter)

    if not stories:
        print("No stories found. Check PI label and permissions.")
        return

    print_report(stories, args.team, args.pi)


if __name__ == "__main__":
    main()
