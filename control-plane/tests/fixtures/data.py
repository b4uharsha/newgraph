"""Test data generators."""

from datetime import UTC, datetime

from control_plane.models import (
    EdgeDefinition,
    Instance,
    InstanceStatus,
    Mapping,
    NodeDefinition,
    PrimaryKeyDefinition,
    PropertyDefinition,
    Snapshot,
    SnapshotStatus,
    User,
)


def create_test_user(
    username: str = "test.user",
    email: str | None = None,
    display_name: str | None = None,
    is_active: bool = True,
) -> User:
    """Create a test user.

    Args:
        username: Username
        email: Email (defaults to {username}@example.com)
        display_name: Display name (defaults to username)
        is_active: Whether user is active

    Returns:
        User domain object (role is request-scoped via RequestUser, not stored)
    """
    return User(
        username=username,
        email=email or f"{username}@example.com",
        display_name=display_name or username.replace(".", " ").title(),
        is_active=is_active,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def create_test_node_definitions(count: int = 2) -> list[NodeDefinition]:
    """Create test node definitions.

    Args:
        count: Number of node definitions to create

    Returns:
        List of NodeDefinition objects
    """
    labels = ["Customer", "Product", "OrderItem", "Supplier", "Category"]
    return [
        NodeDefinition(
            label=labels[i % len(labels)],
            sql=f"SELECT id, name FROM {labels[i % len(labels)].lower()}s",
            primary_key=PrimaryKeyDefinition(name="id", type="STRING"),
            properties=[PropertyDefinition(name="name", type="STRING")],
        )
        for i in range(count)
    ]


def create_test_edge_definitions(count: int = 1) -> list[EdgeDefinition]:
    """Create test edge definitions.

    Args:
        count: Number of edge definitions to create

    Returns:
        List of EdgeDefinition objects
    """
    edges = [
        ("PURCHASED", "Customer", "Product", "customer_id", "product_id"),
        ("CONTAINS", "OrderItem", "Product", "order_id", "product_id"),
        ("SUPPLIES", "Supplier", "Product", "supplier_id", "product_id"),
    ]
    return [
        EdgeDefinition(
            type=edges[i % len(edges)][0],
            sql=f"SELECT * FROM {edges[i % len(edges)][0].lower()}",
            from_node=edges[i % len(edges)][1],
            to_node=edges[i % len(edges)][2],
            from_key=edges[i % len(edges)][3],
            to_key=edges[i % len(edges)][4],
            properties=[],
        )
        for i in range(count)
    ]


def create_test_mapping(
    mapping_id: int = 1,
    owner_username: str = "test.user",
    name: str = "Test Mapping",
    description: str | None = "A test mapping",
    current_version: int = 1,
    node_count: int = 2,
    edge_count: int = 1,
    ttl: str | None = None,
    inactivity_timeout: str | None = None,
) -> Mapping:
    """Create a test mapping.

    Args:
        mapping_id: Mapping ID
        owner_username: Owner's username
        name: Mapping name
        description: Description
        current_version: Current version number
        node_count: Number of node definitions
        edge_count: Number of edge definitions
        ttl: TTL duration
        inactivity_timeout: Inactivity timeout duration

    Returns:
        Mapping domain object
    """
    now = datetime.now(UTC)
    return Mapping(
        id=mapping_id,
        owner_username=owner_username,
        name=name,
        description=description,
        current_version=current_version,
        created_at=now,
        updated_at=now,
        ttl=ttl,
        inactivity_timeout=inactivity_timeout,
        node_definitions=create_test_node_definitions(node_count),
        edge_definitions=create_test_edge_definitions(edge_count),
        change_description=None,
        version_created_at=now,
        version_created_by=owner_username,
    )


def create_test_snapshot(
    snapshot_id: int = 1,
    mapping_id: int = 1,
    mapping_version: int = 1,
    owner_username: str = "test.user",
    name: str = "Test Snapshot",
    description: str | None = "A test snapshot",
    status: SnapshotStatus = SnapshotStatus.READY,
    gcs_path: str | None = None,
    size_bytes: int | None = 1024000,
    ttl: str | None = None,
    inactivity_timeout: str | None = None,
) -> Snapshot:
    """Create a test snapshot.

    Args:
        snapshot_id: Snapshot ID
        mapping_id: Source mapping ID
        mapping_version: Source mapping version
        owner_username: Owner's username
        name: Snapshot name
        description: Description
        status: Snapshot status
        gcs_path: GCS path (auto-generated if None)
        size_bytes: Size in bytes
        ttl: TTL duration
        inactivity_timeout: Inactivity timeout duration

    Returns:
        Snapshot domain object
    """
    now = datetime.now(UTC)
    return Snapshot(
        id=snapshot_id,
        mapping_id=mapping_id,
        mapping_version=mapping_version,
        owner_username=owner_username,
        name=name,
        description=description,
        gcs_path=gcs_path or f"gs://test-bucket/{owner_username}/{mapping_id}/v{mapping_version}/{snapshot_id}/",
        status=status,
        size_bytes=size_bytes if status == SnapshotStatus.READY else None,
        node_counts={"Customer": 1000, "Product": 500} if status == SnapshotStatus.READY else None,
        edge_counts={"PURCHASED": 5000} if status == SnapshotStatus.READY else None,
        progress=None,
        error_message=None,
        created_at=now,
        updated_at=now,
        ttl=ttl,
        inactivity_timeout=inactivity_timeout,
        last_used_at=now if status == SnapshotStatus.READY else None,
    )


def create_test_instance(
    instance_id: int = 1,
    snapshot_id: int = 1,
    owner_username: str = "test.user",
    name: str = "Test Instance",
    description: str | None = "A test instance",
    status: InstanceStatus = InstanceStatus.RUNNING,
    instance_url: str | None = None,
    pod_name: str | None = None,
    ttl: str | None = None,
    inactivity_timeout: str | None = None,
) -> Instance:
    """Create a test instance.

    Args:
        instance_id: Instance ID
        snapshot_id: Source snapshot ID
        owner_username: Owner's username
        name: Instance name
        description: Description
        status: Instance status
        instance_url: Instance URL (auto-generated if running)
        pod_name: Pod name (auto-generated if starting/running)
        ttl: TTL duration
        inactivity_timeout: Inactivity timeout duration

    Returns:
        Instance domain object
    """
    now = datetime.now(UTC)

    if status in (InstanceStatus.STARTING, InstanceStatus.RUNNING) and pod_name is None:
        pod_name = f"graph-instance-{instance_id}-abc123"

    if status == InstanceStatus.RUNNING and instance_url is None:
        instance_url = f"https://graph-{instance_id}.example.com/"

    return Instance(
        id=instance_id,
        snapshot_id=snapshot_id,
        owner_username=owner_username,
        name=name,
        description=description,
        status=status,
        instance_url=instance_url,
        pod_name=pod_name,
        pod_ip="10.0.0.1" if pod_name else None,
        progress=None,
        error_message=None,
        created_at=now,
        updated_at=now,
        started_at=now if status == InstanceStatus.RUNNING else None,
        last_activity_at=now if status == InstanceStatus.RUNNING else None,
        ttl=ttl,
        inactivity_timeout=inactivity_timeout,
        memory_usage_bytes=512000000 if status == InstanceStatus.RUNNING else None,
        disk_usage_bytes=1024000000 if status == InstanceStatus.RUNNING else None,
    )


async def seed_test_data(session, user_repo, mapping_repo, snapshot_repo, instance_repo):
    """Seed test data into the database.

    Creates a complete test scenario with:
    - 3 users (analyst, admin, ops)
    - 2 mappings
    - 3 snapshots (ready, pending, failed)
    - 2 instances (running, starting)

    Args:
        session: Database session
        user_repo: User repository
        mapping_repo: Mapping repository
        snapshot_repo: Snapshot repository
        instance_repo: Instance repository

    Returns:
        Dictionary with created resource IDs
    """
    # Create users (role is per-request via header, not stored in database)
    alice = create_test_user("alice.smith")
    bob = create_test_user("bob.admin")
    charlie = create_test_user("charlie.ops")

    alice = await user_repo.create(alice)
    bob = await user_repo.create(bob)
    charlie = await user_repo.create(charlie)

    # Create mappings
    mapping1 = await mapping_repo.create(
        owner_username=alice.username,
        name="Customer Analysis",
        description="Customer and product relationships",
        node_definitions=create_test_node_definitions(2),
        edge_definitions=create_test_edge_definitions(1),
    )

    mapping2 = await mapping_repo.create(
        owner_username=bob.username,
        name="Supply Chain",
        description="Supplier and inventory graph",
        node_definitions=create_test_node_definitions(3),
        edge_definitions=create_test_edge_definitions(2),
    )

    # Create snapshots
    snapshot1 = await snapshot_repo.create(
        mapping_id=mapping1.id,
        mapping_version=1,
        owner_username=alice.username,
        name="Customer Snapshot v1",
        description="Ready snapshot",
        gcs_path=f"gs://test-bucket/{alice.username}/{mapping1.id}/v1/1/",
    )
    await snapshot_repo.update_status(
        snapshot1.id,
        SnapshotStatus.READY,
        size_bytes=1024000,
        node_counts={"Customer": 1000, "Product": 500},
        edge_counts={"PURCHASED": 5000},
    )

    snapshot2 = await snapshot_repo.create(
        mapping_id=mapping1.id,
        mapping_version=1,
        owner_username=alice.username,
        name="Customer Snapshot v2",
        description="Pending snapshot",
        gcs_path=f"gs://test-bucket/{alice.username}/{mapping1.id}/v1/2/",
    )

    snapshot3 = await snapshot_repo.create(
        mapping_id=mapping2.id,
        mapping_version=1,
        owner_username=bob.username,
        name="Supply Chain Snapshot",
        description="Failed snapshot",
        gcs_path=f"gs://test-bucket/{bob.username}/{mapping2.id}/v1/1/",
    )
    await snapshot_repo.update_status(
        snapshot3.id,
        SnapshotStatus.FAILED,
        error_message="Export failed: Connection timeout",
    )

    # Create instances
    instance1 = await instance_repo.create(
        snapshot_id=snapshot1.id,
        owner_username=alice.username,
        name="Customer Instance 1",
        description="Running instance",
    )
    await instance_repo.update_status(
        instance1.id,
        InstanceStatus.RUNNING,
        pod_name="graph-instance-1-abc123",
        pod_ip="10.0.0.1",
        instance_url="https://graph-1.example.com/",
    )

    instance2 = await instance_repo.create(
        snapshot_id=snapshot1.id,
        owner_username=alice.username,
        name="Customer Instance 2",
        description="Starting instance",
    )

    await session.commit()

    return {
        "users": {
            "alice": alice,
            "bob": bob,
            "charlie": charlie,
        },
        "mappings": {
            "mapping1": mapping1,
            "mapping2": mapping2,
        },
        "snapshots": {
            "ready": snapshot1,
            "pending": snapshot2,
            "failed": snapshot3,
        },
        "instances": {
            "running": instance1,
            "starting": instance2,
        },
    }
