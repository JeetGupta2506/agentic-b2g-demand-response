#!/usr/bin/env python3
"""
MILP-based baseline optimizer for HEMS scheduling.
Provides optimal solutions for comparison with agentic approach.
"""

import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional


def load_reference_prices() -> Tuple[List[float], List[str]]:
    """Load reference prices from test_prices_reference.json"""
    prices_file = Path(__file__).parent.parent / "test_prices_reference.json"

    with open(prices_file, 'r') as f:
        data = json.load(f)

    return data['prices'], data['timeslots']


def find_optimal_appliance_schedule(
    prices: List[float],
    duration_slots: int,
    max_start_slot: Optional[int] = None
) -> Dict:
    """
    Find optimal (minimum cost) schedule for an appliance.

    Args:
        prices: List of 96 price points (EUR/MWh)
        duration_slots: Number of consecutive slots needed
        max_start_slot: Latest slot to finish by (for deadline constraints)

    Returns:
        Dict with optimal_slot, cost, and window_sum
    """
    if max_start_slot is None:
        max_start_slot = 96 - duration_slots

    min_cost = float('inf')
    optimal_slot = 0

    # Exhaustive search over all valid windows
    for start_slot in range(max_start_slot + 1):
        window_prices = prices[start_slot:start_slot + duration_slots]
        window_sum = sum(window_prices)

        if window_sum < min_cost:
            min_cost = window_sum
            optimal_slot = start_slot

    return {
        'optimal_slot': optimal_slot,
        'duration_slots': duration_slots,
        'window_sum': min_cost,
        'cost_eur': min_cost * 1.8 * 0.25 / 1000  # Assuming 1.8kW appliance
    }


def find_most_expensive_3hour_window(prices: List[float]) -> Dict:
    """
    Find the most expensive 3-hour (12 slot) window to avoid.

    Args:
        prices: List of 96 price points (EUR/MWh)

    Returns:
        Dict with start_slot, end_slot, window_sum, and time range
    """
    duration_slots = 12  # 3 hours = 12 × 15-minute slots
    max_cost = float('-inf')
    worst_slot = 0

    # Exhaustive search for maximum cost window
    for start_slot in range(96 - duration_slots + 1):
        window_prices = prices[start_slot:start_slot + duration_slots]
        window_sum = sum(window_prices)

        if window_sum > max_cost:
            max_cost = window_sum
            worst_slot = start_slot

    # Convert to time strings
    start_hour = (worst_slot * 15) // 60
    start_min = (worst_slot * 15) % 60
    end_slot = worst_slot + duration_slots
    end_hour = (end_slot * 15) // 60
    end_min = (end_slot * 15) % 60

    return {
        'start_slot': worst_slot,
        'end_slot': end_slot,
        'duration_slots': duration_slots,
        'start_time': f"{start_hour:02d}:{start_min:02d}",
        'end_time': f"{end_hour:02d}:{end_min:02d}",
        'window_sum': max_cost,
        'avg_price': max_cost / duration_slots
    }


def optimize_all_appliances(prices: List[float]) -> Dict:
    """
    Find optimal schedules for all appliances.

    Returns:
        Dict with optimal schedules for WM, DW, and EV
    """
    results = {}

    # Washing Machine: 8 slots (2 hours)
    results['washing_machine'] = find_optimal_appliance_schedule(
        prices, duration_slots=8
    )

    # Dishwasher: 6 slots (90 minutes)
    results['dishwasher'] = find_optimal_appliance_schedule(
        prices, duration_slots=6
    )

    # EV Charger: 24 slots (6 hours), finish by 7am (slot 28)
    results['ev_charger'] = find_optimal_appliance_schedule(
        prices, duration_slots=24, max_start_slot=4  # Must start by 01:00 to finish by 07:00
    )

    return results


def main():
    """Run MILP baseline optimizations and display results."""
    print("=" * 80)
    print("MILP BASELINE OPTIMIZER")
    print("=" * 80)

    # Load reference prices
    prices, timeslots = load_reference_prices()
    print(f"\nLoaded {len(prices)} price points")
    print(f"Price range: {min(prices):.2f} - {max(prices):.2f} EUR/MWh")

    # 1. Find optimal appliance schedules
    print("\n" + "=" * 80)
    print("OPTIMAL APPLIANCE SCHEDULES (Minimum Cost)")
    print("=" * 80)

    optimal_schedules = optimize_all_appliances(prices)

    for appliance, result in optimal_schedules.items():
        start_slot = result['optimal_slot']
        duration = result['duration_slots']
        end_slot = start_slot + duration

        start_time = timeslots[start_slot]
        end_time = timeslots[end_slot] if end_slot < 96 else "24:00"

        print(f"\n{appliance.upper()}:")
        print(f"  Optimal Slot: {start_slot} ({start_time})")
        print(f"  Duration: {duration} slots ({duration * 15} minutes)")
        print(f"  End Time: {end_time}")
        print(f"  Window Sum: {result['window_sum']:.2f} EUR/MWh")
        print(f"  Cost: €{result['cost_eur']:.4f}")

    # 2. Find most expensive 3-hour window
    print("\n" + "=" * 80)
    print("MOST EXPENSIVE 3-HOUR WINDOW (To Avoid)")
    print("=" * 80)

    worst_window = find_most_expensive_3hour_window(prices)

    print(f"\nWorst 3-Hour Window:")
    print(f"  Start Slot: {worst_window['start_slot']} ({worst_window['start_time']})")
    print(f"  End Slot: {worst_window['end_slot']} ({worst_window['end_time']})")
    print(f"  Time Range: {worst_window['start_time']} - {worst_window['end_time']}")
    print(f"  Window Sum: {worst_window['window_sum']:.2f} EUR/MWh")
    print(f"  Average Price: {worst_window['avg_price']:.2f} EUR/MWh")
    print(f"\n⚠️  Recommendation: Avoid consuming electricity between {worst_window['start_time']} and {worst_window['end_time']}")

    # 3. Save results
    output = {
        'optimal_schedules': optimal_schedules,
        'worst_3hour_window': worst_window,
        'price_statistics': {
            'min_price': min(prices),
            'max_price': max(prices),
            'avg_price': sum(prices) / len(prices),
            'median_price': sorted(prices)[len(prices) // 2]
        }
    }

    output_file = Path(__file__).parent / "baseline_results.json"
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Results saved to {output_file}")
    print("=" * 80)


if __name__ == '__main__':
    main()
