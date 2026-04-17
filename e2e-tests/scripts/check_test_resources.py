#!/usr/bin/env python3
"""Check for orphaned test resources and optionally clean them up.

This script identifies test resources (mappings, snapshots, instances) that
were created during E2E tests but not properly cleaned up. Resources are
considered orphaned if:
1. They match test prefixes (CrudTest-, AlgoTest-, etc.)
2. They are owned by the e2e-test-user
3. They are older than a configurable age threshold

Usage:
    # List orphaned resources
    python scripts/check_test_resources.py --api-url http://localhost:8081

    # List orphaned resources older than 2 hours
    python scripts/check_test_resources.py --older-than 2h

    # Clean up orphaned resources (with confirmation)
    python scripts/check_test_resources.py --cleanup

    # Clean up orphaned resources (no confirmation)
    python scripts/check_test_resources.py --cleanup --force

    # Send alerts if orphans found
    python scripts/check_test_resources.py --alert --threshold 10
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

from graph_olap import GraphOLAPClient
from graph_olap.exceptions import NotFoundError

# Add parent directory to path for utils import
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.constants import TEST_PREFIXES_WITH_DASH, is_test_resource_name

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Use centralized test prefixes from utils.constants
# This ensures consistency between orphan detection and test cleanup
TEST_PREFIXES = TEST_PREFIXES_WITH_DASH


def parse_time_duration(duration_str: str) -> timedelta:
    """Parse time duration string (e.g., '1h', '30m', '2d') to timedelta."""
    if duration_str.endswith('m'):
        return timedelta(minutes=int(duration_str[:-1]))
    elif duration_str.endswith('h'):
        return timedelta(hours=int(duration_str[:-1]))
    elif duration_str.endswith('d'):
        return timedelta(days=int(duration_str[:-1]))
    else:
        raise ValueError(f"Invalid duration format: {duration_str}. Use format like '1h', '30m', '2d'")


def is_test_resource(name: str) -> bool:
    """Check if resource name matches test prefixes."""
    return is_test_resource_name(name)


def is_older_than(created_at: datetime, threshold: timedelta) -> bool:
    """Check if resource is older than threshold."""
    now = datetime.utcnow()
    # Handle timezone-aware datetimes
    if created_at.tzinfo is not None:
        created_at = created_at.replace(tzinfo=None)
    age = now - created_at
    return age > threshold


def find_orphaned_instances(client: GraphOLAPClient, older_than: timedelta = None) -> list[dict]:
    """Find orphaned test instances."""
    orphans = []
    instances = client.instances.list()

    for instance in instances:
        if is_test_resource(instance.name):
            if older_than and not is_older_than(instance.created_at, older_than):
                continue

            orphans.append({
                'type': 'instance',
                'id': instance.id,
                'name': instance.name,
                'status': instance.status,
                'created_at': instance.created_at,
                'owner': getattr(instance, 'owner_username', 'unknown'),
            })

    return orphans


def find_orphaned_snapshots(client: GraphOLAPClient, older_than: timedelta = None) -> list[dict]:
    """Find orphaned test snapshots."""
    orphans = []
    snapshots = client.snapshots.list()

    for snapshot in snapshots:
        if is_test_resource(snapshot.name):
            if older_than and not is_older_than(snapshot.created_at, older_than):
                continue

            orphans.append({
                'type': 'snapshot',
                'id': snapshot.id,
                'name': snapshot.name,
                'status': snapshot.status,
                'created_at': snapshot.created_at,
                'owner': getattr(snapshot, 'owner_username', 'unknown'),
            })

    return orphans


def find_orphaned_mappings(client: GraphOLAPClient, older_than: timedelta = None) -> list[dict]:
    """Find orphaned test mappings."""
    orphans = []
    mappings = client.mappings.list()

    for mapping in mappings:
        if is_test_resource(mapping.name):
            if older_than and not is_older_than(mapping.created_at, older_than):
                continue

            orphans.append({
                'type': 'mapping',
                'id': mapping.id,
                'name': mapping.name,
                'created_at': mapping.created_at,
                'owner': getattr(mapping, 'owner_username', 'unknown'),
            })

    return orphans


def cleanup_resource(client: GraphOLAPClient, resource: dict) -> bool:
    """Clean up a single resource. Returns True if successful."""
    try:
        resource_type = resource['type']
        resource_id = resource['id']

        if resource_type == 'instance':
            client.instances.delete(resource_id)
        elif resource_type == 'snapshot':
            client.snapshots.delete(resource_id)
        elif resource_type == 'mapping':
            client.mappings.delete(resource_id)
        else:
            logger.error(f"Unknown resource type: {resource_type}")
            return False

        # Verify deletion
        try:
            if resource_type == 'instance':
                client.instances.get(resource_id)
            elif resource_type == 'snapshot':
                client.snapshots.get(resource_id)
            elif resource_type == 'mapping':
                client.mappings.get(resource_id)

            # If we got here, resource still exists
            logger.warning(f"Resource {resource_type} {resource_id} still exists after deletion")
            return False

        except NotFoundError:
            # Resource successfully deleted
            return True

    except Exception as e:
        logger.error(f"Failed to cleanup {resource['type']} {resource['id']}: {e}")
        return False


def print_report(orphans: list[dict]):
    """Print a formatted report of orphaned resources."""
    if not orphans:
        print("\n✅ No orphaned test resources found!")
        return

    print(f"\n⚠️  Found {len(orphans)} orphaned test resource(s):\n")

    # Group by type
    by_type = {}
    for resource in orphans:
        resource_type = resource['type']
        if resource_type not in by_type:
            by_type[resource_type] = []
        by_type[resource_type].append(resource)

    # Print grouped results
    for resource_type, resources in sorted(by_type.items()):
        print(f"{resource_type.upper()}S ({len(resources)}):")
        for resource in sorted(resources, key=lambda r: r['created_at']):
            age = datetime.utcnow() - resource['created_at'].replace(tzinfo=None)
            age_str = f"{age.days}d {age.seconds//3600}h" if age.days > 0 else f"{age.seconds//3600}h {(age.seconds//60)%60}m"

            status = f" (status={resource.get('status', 'unknown')})" if 'status' in resource else ""
            print(f"  - {resource['name']} (id={resource['id']}, age={age_str}{status})")
        print()


def send_alert(orphan_count: int, threshold: int):
    """Send alert if orphan count exceeds threshold."""
    if orphan_count <= threshold:
        return

    message = f"⚠️ WARNING: {orphan_count} orphaned test resources found (threshold: {threshold})"

    # Log to stderr for monitoring systems to pick up
    logger.error(message)

    # In a production environment, you would send alerts via:
    # - Slack webhook
    # - PagerDuty
    # - Email
    # - Prometheus Alertmanager
    # etc.

    print(f"\n{message}")
    print("NOTE: Configure alerting in send_alert() function for production use")


def main():
    parser = argparse.ArgumentParser(
        description="Check for orphaned test resources and optionally clean them up",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List orphaned resources
  %(prog)s --api-url http://localhost:8081

  # List resources older than 1 hour
  %(prog)s --older-than 1h

  # Clean up orphaned resources
  %(prog)s --cleanup

  # Clean up without confirmation
  %(prog)s --cleanup --force

  # Send alert if more than 10 orphans found
  %(prog)s --alert --threshold 10
        """
    )

    parser.add_argument(
        '--api-url',
        default='http://localhost:8081',
        help='Control Plane API URL (default: http://localhost:8081)'
    )
    parser.add_argument(
        '--username',
        default='e2e-test-user',
        help='Username to check resources for (default: e2e-test-user)'
    )
    parser.add_argument(
        '--older-than',
        help='Only show resources older than this duration (e.g., 1h, 30m, 2d)'
    )
    parser.add_argument(
        '--cleanup',
        action='store_true',
        help='Clean up orphaned resources'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Clean up without confirmation prompt'
    )
    parser.add_argument(
        '--alert',
        action='store_true',
        help='Send alert if orphan count exceeds threshold'
    )
    parser.add_argument(
        '--threshold',
        type=int,
        default=10,
        help='Alert threshold (default: 10)'
    )

    args = parser.parse_args()

    # Parse time threshold
    older_than = None
    if args.older_than:
        try:
            older_than = parse_time_duration(args.older_than)
            logger.info(f"Filtering resources older than {older_than}")
        except ValueError as e:
            logger.error(str(e))
            sys.exit(1)

    # Connect to Control Plane
    logger.info(f"Connecting to {args.api_url} as {args.username}")
    client = GraphOLAPClient(
        api_url=args.api_url,
        username=args.username,
    )

    # Find orphaned resources
    logger.info("Scanning for orphaned test resources...")
    orphaned_instances = find_orphaned_instances(client, older_than)
    orphaned_snapshots = find_orphaned_snapshots(client, older_than)
    orphaned_mappings = find_orphaned_mappings(client, older_than)

    all_orphans = orphaned_instances + orphaned_snapshots + orphaned_mappings

    # Print report
    print_report(all_orphans)

    # Send alert if requested
    if args.alert:
        send_alert(len(all_orphans), args.threshold)

    # Clean up if requested
    if args.cleanup and all_orphans:
        if not args.force:
            response = input(f"\n⚠️  This will delete {len(all_orphans)} resource(s). Continue? [y/N] ")
            if response.lower() != 'y':
                print("Cleanup cancelled.")
                sys.exit(0)

        print("\nCleaning up orphaned resources...")

        # Clean up in dependency order: instances → snapshots → mappings
        success_count = 0
        failure_count = 0

        for resource_type in ['instance', 'snapshot', 'mapping']:
            resources = [r for r in all_orphans if r['type'] == resource_type]
            for resource in resources:
                logger.info(f"Deleting {resource['type']} {resource['id']} ({resource['name']})")
                if cleanup_resource(client, resource):
                    success_count += 1
                    print(f"  ✓ Deleted {resource['type']} {resource['name']}")
                else:
                    failure_count += 1
                    print(f"  ✗ Failed to delete {resource['type']} {resource['name']}")

        print(f"\nCleanup complete: {success_count} deleted, {failure_count} failed")

        if failure_count > 0:
            sys.exit(1)

    elif args.cleanup:
        print("\nNo orphaned resources to clean up.")

    # Exit with error code if orphans found (for CI/CD)
    if all_orphans:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
