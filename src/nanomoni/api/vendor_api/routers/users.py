"""User API routes (Vendor)."""

from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ....application.vendor.dtos import CreateUserDTO, UpdateUserDTO, UserResponseDTO
from ....application.vendor.use_cases.user import UserService
from ..dependencies import get_user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", response_model=UserResponseDTO, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: CreateUserDTO, user_service: UserService = Depends(get_user_service)
) -> UserResponseDTO:
    """Create a new user."""
    try:
        return await user_service.create_user(user_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/", response_model=List[UserResponseDTO])
async def get_users(
    skip: int = 0,
    limit: int = 100,
    user_service: UserService = Depends(get_user_service),
) -> List[UserResponseDTO]:
    """Get all users with pagination."""
    return await user_service.get_all_users(skip=skip, limit=limit)


@router.get("/{user_id}", response_model=UserResponseDTO)
async def get_user(
    user_id: UUID, user_service: UserService = Depends(get_user_service)
) -> UserResponseDTO:
    """Get user by ID."""
    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.get("/email/{email}", response_model=UserResponseDTO)
async def get_user_by_email(
    email: str, user_service: UserService = Depends(get_user_service)
) -> UserResponseDTO:
    """Get user by email."""
    user = await user_service.get_user_by_email(email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.put("/{user_id}", response_model=UserResponseDTO)
async def update_user(
    user_id: UUID,
    user_data: UpdateUserDTO,
    user_service: UserService = Depends(get_user_service),
) -> UserResponseDTO:
    """Update a user."""
    try:
        user = await user_service.update_user(user_id, user_data)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID, user_service: UserService = Depends(get_user_service)
):
    """Delete a user."""
    success = await user_service.delete_user(user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )


@router.patch("/{user_id}/deactivate", response_model=UserResponseDTO)
async def deactivate_user(
    user_id: UUID, user_service: UserService = Depends(get_user_service)
) -> UserResponseDTO:
    """Deactivate a user."""
    user = await user_service.deactivate_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.patch("/{user_id}/activate", response_model=UserResponseDTO)
async def activate_user(
    user_id: UUID, user_service: UserService = Depends(get_user_service)
) -> UserResponseDTO:
    """Activate a user."""
    user = await user_service.activate_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user
