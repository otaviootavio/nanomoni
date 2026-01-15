"""Adaptive PI controller for race condition testing.

This controller dynamically adjusts the delay between concurrent requests
to target a 50% race condition rate, maximizing the chance of triggering
race conditions during testing.
"""

from __future__ import annotations

from typing import List, Optional


class AdaptiveDelayController:
    """PI Controller with dynamic gain scheduling for targeting 50% race rate."""

    def __init__(
        self,
        initial_kp: float = 0.001,
        ki: float = 0.0001,
        gain_reduction_factor: float = 0.5,
        min_kp: float = 0.00005,
    ):
        self.current_delay: float = 0.0
        self.kp: float = initial_kp
        self.ki: float = ki
        self.integral_error: float = 0.0
        self.gain_reduction_factor: float = gain_reduction_factor
        self.min_kp: float = min_kp
        self._prev_delay_sign: int = 0
        self.delay_history: List[float] = []

    def update(self, step_outcome: float, iteration: Optional[int] = None) -> float:
        """
        Update delay based on outcome.

        Args:
            step_outcome: 1.0 for lost update, 0.0 for correct, 0.5 for error/neutral
            iteration: Optional iteration number for logging zero crossings

        Returns:
            Updated delay value (positive = delay B, negative = delay A)
        """
        # Calculate Error
        error = step_outcome - 0.5

        # Update Integral
        self.integral_error += error
        self.integral_error = max(-100.0, min(100.0, self.integral_error))

        # PI Update
        self.current_delay += (self.kp * error) + (self.ki * self.integral_error)

        # Dynamic Gain Scheduling (Zero Crossing Detection)
        current_sign = 0
        if self.current_delay > 1e-6:
            current_sign = 1
        elif self.current_delay < -1e-6:
            current_sign = -1

        if (
            self._prev_delay_sign != 0
            and current_sign != 0
            and current_sign != self._prev_delay_sign
        ):
            old_kp = self.kp
            self.kp = max(self.min_kp, self.kp * self.gain_reduction_factor)
            if iteration is not None and self.kp < old_kp:
                print(
                    f"  [Auto-Tune] Zero crossing at Iter {iteration}. "
                    f"Kp: {old_kp:.6f} -> {self.kp:.6f}"
                )

        if current_sign != 0:
            self._prev_delay_sign = current_sign

        self.delay_history.append(self.current_delay)
        return self.current_delay

    def avg_delay(self, window: int = 50) -> float:
        """Get average delay over last N iterations."""
        if not self.delay_history:
            return 0.0
        recent = self.delay_history[-window:]
        return sum(recent) / len(recent)
