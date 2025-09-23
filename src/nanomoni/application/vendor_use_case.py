"""Use cases for the vendor application layer."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID
import httpx

from ..domain.vendor.entities import User, Task, OffChainTx
from ..domain.vendor.user_repository import UserRepository
from ..domain.vendor.task_repository import TaskRepository
from ..domain.vendor.off_chain_tx_repository import OffChainTxRepository
from .vendor_dtos import (
    CreateUserDTO,
    UpdateUserDTO,
    UserResponseDTO,
    CreateTaskDTO,
    UpdateTaskDTO,
    TaskResponseDTO,
    ReceivePaymentDTO,
    OffChainTxResponseDTO,
)
from ..crypto.certificates import (
    verify_envelope,
    load_public_key_from_der_b64,
    deserialize_off_chain_tx,
)


class UserService:
    """Service for user-related operations."""

    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    async def create_user(self, dto: CreateUserDTO) -> UserResponseDTO:
        """Create a new user."""
        email = dto.email.lower()
        # Check if user already exists
        if await self.user_repository.exists_by_email(email):
            raise ValueError("User with this email already exists")

        # Create user entity
        user = User(name=dto.name, email=email)

        # Save user
        created_user = await self.user_repository.create(user)

        return UserResponseDTO(**created_user.model_dump())

    async def get_user_by_id(self, user_id: UUID) -> Optional[UserResponseDTO]:
        """Get user by ID."""
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            return None

        return UserResponseDTO(**user.model_dump())

    async def get_user_by_email(self, email: str) -> Optional[UserResponseDTO]:
        """Get user by email."""
        user = await self.user_repository.get_by_email(email.lower())
        if not user:
            return None

        return UserResponseDTO(**user.model_dump())

    async def get_all_users(
        self, skip: int = 0, limit: int = 100
    ) -> List[UserResponseDTO]:
        """Get all users with pagination."""
        users = await self.user_repository.get_all(skip=skip, limit=limit)
        return [UserResponseDTO(**user.model_dump()) for user in users]

    async def update_user(
        self, user_id: UUID, dto: UpdateUserDTO
    ) -> Optional[UserResponseDTO]:
        """Update user details."""
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            return None

        # Determine new email if provided and perform duplicate check only when changing
        new_email: Optional[str] = None
        if dto.email is not None:
            candidate = dto.email.lower()
            if candidate != user.email.lower():
                if await self.user_repository.exists_by_email(candidate):
                    raise ValueError("User with this email already exists")
            new_email = candidate

        # Use entity method to set updated_at and apply provided fields
        user.update_details(name=dto.name, email=new_email)

        updated_user = await self.user_repository.update(user)

        return UserResponseDTO(**updated_user.model_dump())

    async def delete_user(self, user_id: UUID) -> bool:
        """Delete a user by ID."""
        return await self.user_repository.delete(user_id)

    async def deactivate_user(self, user_id: UUID) -> Optional[UserResponseDTO]:
        """Deactivate a user by ID."""
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            return None

        user.deactivate()
        updated_user = await self.user_repository.update(user)

        return UserResponseDTO(**updated_user.model_dump())

    async def activate_user(self, user_id: UUID) -> Optional[UserResponseDTO]:
        """Activate a user by ID."""
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            return None

        user.activate()
        updated_user = await self.user_repository.update(user)

        return UserResponseDTO(**updated_user.model_dump())


class TaskService:
    """Service for task-related operations."""

    def __init__(
        self, task_repository: TaskRepository, user_repository: UserRepository
    ):
        self.task_repository = task_repository
        self.user_repository = user_repository

    async def create_task(self, dto: CreateTaskDTO) -> TaskResponseDTO:
        """Create a new task."""
        # Verify user exists
        user = await self.user_repository.get_by_id(dto.user_id)
        if not user:
            raise ValueError("User not found")

        # Create task entity
        task = Task(title=dto.title, description=dto.description, user_id=dto.user_id)

        # Save task
        created_task = await self.task_repository.create(task)

        return TaskResponseDTO(**created_task.model_dump())

    async def get_task_by_id(self, task_id: UUID) -> Optional[TaskResponseDTO]:
        """Get task by ID."""
        task = await self.task_repository.get_by_id(task_id)
        if not task:
            return None

        return TaskResponseDTO(**task.model_dump())

    async def get_all_tasks(
        self, skip: int = 0, limit: int = 100
    ) -> List[TaskResponseDTO]:
        """Get all tasks with pagination."""
        tasks = await self.task_repository.get_all(skip=skip, limit=limit)
        return [TaskResponseDTO(**task.model_dump()) for task in tasks]

    async def get_tasks_by_user(
        self, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> List[TaskResponseDTO]:
        """Get tasks by user ID."""
        tasks = await self.task_repository.get_by_user_id(
            user_id, skip=skip, limit=limit
        )
        return [TaskResponseDTO(**task.model_dump()) for task in tasks]

    async def get_tasks_by_status(
        self, status: str, skip: int = 0, limit: int = 100
    ) -> List[TaskResponseDTO]:
        """Get tasks by status."""
        tasks = await self.task_repository.get_by_status(status, skip=skip, limit=limit)
        return [TaskResponseDTO(**task.model_dump()) for task in tasks]

    async def update_task(
        self, task_id: UUID, dto: UpdateTaskDTO
    ) -> Optional[TaskResponseDTO]:
        """Update task details."""
        task = await self.task_repository.get_by_id(task_id)
        if not task:
            return None

        # Update provided fields via entity method to set updated_at
        if dto.description is not None:
            task.update_details(title=dto.title, description=dto.description)
        else:
            task.update_details(title=dto.title)
        if dto.status is not None:
            task.status = dto.status

        updated_task = await self.task_repository.update(task)

        return TaskResponseDTO(**updated_task.model_dump())

    async def delete_task(self, task_id: UUID) -> bool:
        """Delete a task by ID."""
        return await self.task_repository.delete(task_id)

    async def start_task(self, task_id: UUID) -> Optional[TaskResponseDTO]:
        """Start a task."""
        task = await self.task_repository.get_by_id(task_id)
        if not task:
            return None
        task.start()
        updated = await self.task_repository.update(task)
        return TaskResponseDTO(**updated.model_dump())

    async def complete_task(self, task_id: UUID) -> Optional[TaskResponseDTO]:
        """Complete a task."""
        task = await self.task_repository.get_by_id(task_id)
        if not task:
            return None
        task.complete()
        updated = await self.task_repository.update(task)
        return TaskResponseDTO(**updated.model_dump())

    async def fail_task(self, task_id: UUID) -> Optional[TaskResponseDTO]:
        """Fail a task."""
        task = await self.task_repository.get_by_id(task_id)
        if not task:
            return None
        task.fail()
        updated = await self.task_repository.update(task)
        return TaskResponseDTO(**updated.model_dump())


class PaymentService:
    """Service for handling off-chain payment transactions."""

    def __init__(self, off_chain_tx_repository: OffChainTxRepository, issuer_base_url: str):
        self.off_chain_tx_repository = off_chain_tx_repository
        self.issuer_base_url = issuer_base_url

    async def _verify_payment_channel_exists(self, computed_id: str) -> None:
        """Verify that the payment channel exists on the issuer side."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.issuer_base_url}/issuer/payment-channel/{computed_id}"
                )
                response.raise_for_status()
                channel_data = response.json()
                
                # Check if channel is closed
                if channel_data.get("is_closed", False):
                    raise ValueError("Payment channel is closed")
                    
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ValueError("Payment channel not found on issuer")
            raise ValueError(f"Failed to verify payment channel: {e}")
        except httpx.RequestError as e:
            raise ValueError(f"Could not connect to issuer: {e}")

    async def receive_payment(self, dto: ReceivePaymentDTO) -> OffChainTxResponseDTO:
        """Receive and validate an off-chain payment from a client."""
        # 1) Verify client's signature
        client_public_key = load_public_key_from_der_b64(dto.client_public_key_der_b64)
        verify_envelope(client_public_key, dto.envelope)

        # 2) Decode and validate payload
        payload = deserialize_off_chain_tx(dto.envelope)

        # 3) Get the latest transaction for this payment channel to check for double spending
        latest_tx = await self.off_chain_tx_repository.get_latest_by_computed_id(
            payload.computed_id
        )
        prev_owed_amount = latest_tx.owed_amount if latest_tx else 0

        # 3.1) If this is the first payment for this channel, verify it exists on issuer
        if latest_tx is None:
            await self._verify_payment_channel_exists(payload.computed_id)

        # 4) Check for double spending - owed amount must be increasing
        if payload.owed_amount <= prev_owed_amount:
            raise ValueError(
                f"Owed amount must be increasing. Got {payload.owed_amount}, expected > {prev_owed_amount}"
            )

        # 5) Create and store the off-chain transaction
        off_chain_tx = OffChainTx(
            computed_id=payload.computed_id,
            client_public_key_der_b64=payload.client_public_key_der_b64,
            vendor_public_key_der_b64=payload.vendor_public_key_der_b64,
            owed_amount=payload.owed_amount,
            payload_b64=dto.envelope.payload_b64,
            signature_b64=dto.envelope.signature_b64,
        )

        # Save to repository
        created_tx = await self.off_chain_tx_repository.create(off_chain_tx)

        return OffChainTxResponseDTO(**created_tx.model_dump())

    async def get_payment_by_id(self, tx_id: UUID) -> Optional[OffChainTxResponseDTO]:
        """Get an off-chain transaction by ID."""
        tx = await self.off_chain_tx_repository.get_by_id(tx_id)
        if not tx:
            return None
        return OffChainTxResponseDTO(**tx.model_dump())

    async def get_payments_by_channel(
        self, computed_id: str
    ) -> List[OffChainTxResponseDTO]:
        """Get all payments for a payment channel."""
        txs = await self.off_chain_tx_repository.get_by_computed_id(computed_id)
        return [OffChainTxResponseDTO(**tx.model_dump()) for tx in txs]
