"""Unit tests for repository layer."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.repositories.config import GlobalConfigRepository
from control_plane.repositories.mappings import MappingFilters, MappingRepository, Pagination, Sort
from control_plane.repositories.users import UserRepository
from tests.fixtures.data import (
    create_test_edge_definitions,
    create_test_node_definitions,
    create_test_user,
)


class TestUserRepository:
    """Tests for UserRepository."""

    @pytest_asyncio.fixture
    async def user_repo(self, db_session: AsyncSession) -> UserRepository:
        return UserRepository(db_session)

    @pytest.mark.asyncio
    async def test_create_user(self, user_repo: UserRepository):
        """Test creating a new user."""
        user = create_test_user("alice.smith")
        created = await user_repo.create(user)

        assert created.username == "alice.smith"
        assert created.email == "alice.smith@example.com"
        assert created.is_active is True
        assert created.created_at is not None

    @pytest.mark.asyncio
    async def test_get_by_username(self, user_repo: UserRepository):
        """Test fetching user by username."""
        user = create_test_user("bob.jones")
        await user_repo.create(user)

        found = await user_repo.get_by_username("bob.jones")
        assert found is not None
        assert found.username == "bob.jones"

    @pytest.mark.asyncio
    async def test_get_by_username_not_found(self, user_repo: UserRepository):
        """Test fetching non-existent user returns None."""
        found = await user_repo.get_by_username("nonexistent")
        assert found is None

    @pytest.mark.asyncio
    async def test_get_by_email(self, user_repo: UserRepository):
        """Test fetching user by email."""
        user = create_test_user("charlie.wilson")
        await user_repo.create(user)

        found = await user_repo.get_by_email("charlie.wilson@example.com")
        assert found is not None
        assert found.username == "charlie.wilson"

    @pytest.mark.asyncio
    async def test_list_users(self, user_repo: UserRepository):
        """Test listing users with pagination."""
        # Create multiple users
        for i in range(5):
            await user_repo.create(create_test_user(f"user{i}"))

        users, total = await user_repo.list_users(limit=3, offset=0)
        assert len(users) == 3
        assert total == 5

    @pytest.mark.asyncio
    async def test_list_users_filter_by_is_active(self, user_repo: UserRepository):
        """Test filtering users by active status."""
        await user_repo.create(create_test_user("active1", is_active=True))
        await user_repo.create(create_test_user("active2", is_active=True))
        await user_repo.create(create_test_user("inactive1", is_active=False))

        active_users, total = await user_repo.list_users(is_active=True)
        assert len(active_users) == 2
        assert total == 2
        assert all(u.is_active for u in active_users)

    @pytest.mark.asyncio
    async def test_update_user(self, user_repo: UserRepository):
        """Test updating a user."""
        user = create_test_user("update.test")
        created = await user_repo.create(user)

        created.display_name = "Updated Name"
        updated = await user_repo.update(created)

        assert updated.display_name == "Updated Name"

    @pytest.mark.asyncio
    async def test_deactivate_user(self, user_repo: UserRepository):
        """Test deactivating a user."""
        user = create_test_user("deactivate.test")
        await user_repo.create(user)

        result = await user_repo.deactivate("deactivate.test")
        assert result is True

        found = await user_repo.get_by_username("deactivate.test")
        assert found is not None
        assert found.is_active is False

    @pytest.mark.asyncio
    async def test_exists(self, user_repo: UserRepository):
        """Test checking if user exists."""
        user = create_test_user("exists.test")
        await user_repo.create(user)

        assert await user_repo.exists("exists.test") is True
        assert await user_repo.exists("nonexistent") is False


class TestMappingRepository:
    """Tests for MappingRepository."""

    @pytest_asyncio.fixture
    async def mapping_repo(self, db_session: AsyncSession) -> MappingRepository:
        return MappingRepository(db_session)

    @pytest_asyncio.fixture
    async def user_repo(self, db_session: AsyncSession) -> UserRepository:
        return UserRepository(db_session)

    @pytest_asyncio.fixture
    async def test_user(self, user_repo: UserRepository):
        """Create a test user for mapping ownership."""
        user = create_test_user("mapping.owner")
        return await user_repo.create(user)

    @pytest.mark.asyncio
    async def test_create_mapping(self, mapping_repo: MappingRepository, test_user):
        """Test creating a new mapping."""
        node_defs = create_test_node_definitions(2)
        edge_defs = create_test_edge_definitions(1)

        mapping = await mapping_repo.create(
            owner_username=test_user.username,
            name="Test Mapping",
            description="A test mapping",
            node_definitions=node_defs,
            edge_definitions=edge_defs,
        )

        assert mapping.id is not None
        assert mapping.name == "Test Mapping"
        assert mapping.owner_username == test_user.username
        assert mapping.current_version == 1
        assert len(mapping.node_definitions) == 2
        assert len(mapping.edge_definitions) == 1

    @pytest.mark.asyncio
    async def test_get_by_id(self, mapping_repo: MappingRepository, test_user):
        """Test fetching mapping by ID."""
        mapping = await mapping_repo.create(
            owner_username=test_user.username,
            name="Fetch Test",
            description=None,
            node_definitions=create_test_node_definitions(1),
            edge_definitions=[],
        )

        found = await mapping_repo.get_by_id(mapping.id)
        assert found is not None
        assert found.name == "Fetch Test"
        assert found.current_version == 1

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, mapping_repo: MappingRepository):
        """Test fetching non-existent mapping returns None."""
        found = await mapping_repo.get_by_id(99999)
        assert found is None

    @pytest.mark.asyncio
    async def test_list_mappings(self, mapping_repo: MappingRepository, test_user):
        """Test listing mappings with pagination."""
        for i in range(5):
            await mapping_repo.create(
                owner_username=test_user.username,
                name=f"Mapping {i}",
                description=None,
                node_definitions=create_test_node_definitions(1),
                edge_definitions=[],
            )

        filters = MappingFilters()
        pagination = Pagination(limit=3, offset=0)
        sort = Sort(field="created_at", order="desc")

        mappings, total = await mapping_repo.list_mappings(filters, pagination, sort)
        assert len(mappings) == 3
        assert total == 5

    @pytest.mark.asyncio
    async def test_list_mappings_filter_by_owner(
        self, mapping_repo: MappingRepository, user_repo: UserRepository
    ):
        """Test filtering mappings by owner."""
        user1 = await user_repo.create(create_test_user("owner1"))
        user2 = await user_repo.create(create_test_user("owner2"))

        await mapping_repo.create(
            owner_username=user1.username,
            name="User1 Mapping",
            description=None,
            node_definitions=create_test_node_definitions(1),
            edge_definitions=[],
        )
        await mapping_repo.create(
            owner_username=user2.username,
            name="User2 Mapping",
            description=None,
            node_definitions=create_test_node_definitions(1),
            edge_definitions=[],
        )

        filters = MappingFilters(owner=user1.username)
        mappings, total = await mapping_repo.list_mappings(filters, Pagination(), Sort())
        assert len(mappings) == 1
        assert mappings[0].owner_username == user1.username

    @pytest.mark.asyncio
    async def test_list_mappings_search(self, mapping_repo: MappingRepository, test_user):
        """Test searching mappings by name."""
        await mapping_repo.create(
            owner_username=test_user.username,
            name="Customer Graph",
            description="Graph of customers",
            node_definitions=create_test_node_definitions(1),
            edge_definitions=[],
        )
        await mapping_repo.create(
            owner_username=test_user.username,
            name="Product Catalog",
            description="Product relationships",
            node_definitions=create_test_node_definitions(1),
            edge_definitions=[],
        )

        filters = MappingFilters(search="Customer")
        mappings, total = await mapping_repo.list_mappings(filters, Pagination(), Sort())
        assert len(mappings) == 1
        assert "Customer" in mappings[0].name

    @pytest.mark.asyncio
    async def test_update_mapping_creates_version(self, mapping_repo: MappingRepository, test_user):
        """Test that updating definitions creates a new version."""
        mapping = await mapping_repo.create(
            owner_username=test_user.username,
            name="Version Test",
            description=None,
            node_definitions=create_test_node_definitions(1),
            edge_definitions=[],
        )
        assert mapping.current_version == 1

        # Update with new definitions
        updated = await mapping_repo.update(
            mapping_id=mapping.id,
            updated_by=test_user.username,
            node_definitions=create_test_node_definitions(2),
            change_description="Added new node",
        )

        assert updated is not None
        assert updated.current_version == 2
        assert len(updated.node_definitions) == 2

    @pytest.mark.asyncio
    async def test_delete_mapping(self, mapping_repo: MappingRepository, test_user):
        """Test deleting a mapping."""
        mapping = await mapping_repo.create(
            owner_username=test_user.username,
            name="Delete Test",
            description=None,
            node_definitions=create_test_node_definitions(1),
            edge_definitions=[],
        )

        result = await mapping_repo.delete(mapping.id)
        assert result is True

        found = await mapping_repo.get_by_id(mapping.id)
        assert found is None

    @pytest.mark.asyncio
    async def test_list_versions(self, mapping_repo: MappingRepository, test_user):
        """Test listing mapping versions."""
        mapping = await mapping_repo.create(
            owner_username=test_user.username,
            name="Version History",
            description=None,
            node_definitions=create_test_node_definitions(1),
            edge_definitions=[],
        )

        # Create version 2
        await mapping_repo.update(
            mapping_id=mapping.id,
            updated_by=test_user.username,
            node_definitions=create_test_node_definitions(2),
            change_description="Version 2",
        )

        versions = await mapping_repo.list_versions(mapping.id)
        assert len(versions) == 2
        assert versions[0].version == 2  # Ordered by version DESC
        assert versions[1].version == 1


class TestGlobalConfigRepository:
    """Tests for GlobalConfigRepository."""

    @pytest_asyncio.fixture
    async def config_repo(self, db_session: AsyncSession) -> GlobalConfigRepository:
        return GlobalConfigRepository(db_session)

    @pytest_asyncio.fixture
    async def user_repo(self, db_session: AsyncSession) -> UserRepository:
        return UserRepository(db_session)

    @pytest_asyncio.fixture
    async def ops_user(self, user_repo: UserRepository):
        """Create a user for config updates."""
        user = create_test_user("config.ops")
        return await user_repo.create(user)

    @pytest.mark.asyncio
    async def test_seed_defaults(self, config_repo: GlobalConfigRepository, ops_user):
        """Test seeding default configuration."""
        count = await config_repo.seed_defaults(ops_user.username)
        assert count > 0

        # Verify some values
        ttl = await config_repo.get_value("lifecycle.instance.default_ttl")
        assert ttl == "PT24H"

    @pytest.mark.asyncio
    async def test_get_and_set(self, config_repo: GlobalConfigRepository, ops_user):
        """Test getting and setting config values."""
        await config_repo.set(
            key="test.config",
            value="test_value",
            updated_by=ops_user.username,
            description="Test configuration",
        )

        value = await config_repo.get_value("test.config")
        assert value == "test_value"

    @pytest.mark.asyncio
    async def test_get_int(self, config_repo: GlobalConfigRepository, ops_user):
        """Test getting integer config value."""
        await config_repo.set(
            key="test.int",
            value="42",
            updated_by=ops_user.username,
        )

        value = await config_repo.get_int("test.int")
        assert value == 42

    @pytest.mark.asyncio
    async def test_get_bool(self, config_repo: GlobalConfigRepository, ops_user):
        """Test getting boolean config value."""
        await config_repo.set(
            key="test.bool.true",
            value="1",
            updated_by=ops_user.username,
        )
        await config_repo.set(
            key="test.bool.false",
            value="0",
            updated_by=ops_user.username,
        )

        assert await config_repo.get_bool("test.bool.true") is True
        assert await config_repo.get_bool("test.bool.false") is False

    @pytest.mark.asyncio
    async def test_get_concurrency_limits(self, config_repo: GlobalConfigRepository, ops_user):
        """Test getting concurrency limits."""
        await config_repo.seed_defaults(ops_user.username)

        limits = await config_repo.get_concurrency_limits()
        assert "per_analyst" in limits
        assert "cluster_total" in limits
        assert limits["per_analyst"] == 10
        assert limits["cluster_total"] == 50

    @pytest.mark.asyncio
    async def test_get_export_config_default(
        self, config_repo: GlobalConfigRepository, ops_user
    ):
        """Test getting export config with default value."""
        await config_repo.seed_defaults(ops_user.username)

        config = await config_repo.get_export_config()
        assert config["max_duration_seconds"] == 3600
        assert config["updated_at"] is not None
        assert config["updated_by"] == ops_user.username

    @pytest.mark.asyncio
    async def test_get_export_config_custom(
        self, config_repo: GlobalConfigRepository, ops_user
    ):
        """Test getting export config after custom value set."""
        await config_repo.set(
            key="export.max_duration_seconds",
            value="7200",
            updated_by=ops_user.username,
            description="Custom export duration",
        )

        config = await config_repo.get_export_config()
        assert config["max_duration_seconds"] == 7200
        assert config["updated_by"] == ops_user.username
