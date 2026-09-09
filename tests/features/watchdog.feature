Feature: Safety-net watchdog
  The Function's timer enforces the session ceiling and heartbeat, and never reads the player count.

  Background:
    Given max_session_hours is 12
    And heartbeat_stale_minutes is 20

  @unit
  Scenario: A healthy session is left alone
    Given the bonfire is lit with session_started_at 3 hours ago
    And last_heartbeat is 1 minute ago
    When the safety-net timer runs
    Then no VM deallocate is requested
    And no message is posted
    And the state row is unchanged

  @unit
  Scenario: The ceiling is announced one hour ahead
    Given the bonfire is lit with session_started_at 11 hours 5 minutes ago
    And last_heartbeat is 1 minute ago and ceiling_warned is false
    When the safety-net timer runs
    Then the webhook receives message "watchdog_ceiling_warning" with h 11
    And ceiling_warned is true
    And a "watchdog/ceiling_warning" event is recorded
    And no VM deallocate is requested

  @unit
  Scenario: The ceiling warning is posted once
    Given the bonfire is lit with session_started_at 11 hours 20 minutes ago
    And last_heartbeat is 1 minute ago and ceiling_warned is true
    When the safety-net timer runs
    Then no message is posted

  @unit
  Scenario: The session ceiling extinguishes regardless of players
    Given the bonfire is lit with session_started_at 12 hours 1 minute ago
    And last_heartbeat is 1 minute ago and last_player_count is 4
    When the safety-net timer runs
    Then the state row has vm_state "extinguishing" and session_ended_at now
    And a VM deallocate is requested by the Function exactly once
    And the webhook receives message "watchdog_ceiling"
    And a "watchdog/ceiling" event is recorded with player_count 4

  @unit
  Scenario: A missing heartbeat extinguishes
    Given the bonfire is lit with session_started_at 2 hours ago
    And last_heartbeat is 21 minutes ago
    When the safety-net timer runs
    Then the state row has vm_state "extinguishing"
    And a VM deallocate is requested by the Function exactly once
    And the webhook receives message "watchdog_heartbeat"
    And a "watchdog/heartbeat_missing" event is recorded

  @unit
  Scenario: A missing heartbeat while igniting is tolerated for heartbeat_stale_minutes
    Given the bonfire is igniting since 3 minutes ago
    And last_heartbeat is null
    When the safety-net timer runs
    Then no VM deallocate is requested

  @unit
  Scenario: A boot that never reports in is a failed ignite
    Given the bonfire is igniting since 21 minutes ago
    And last_heartbeat is null
    And the VM power state is running
    When the safety-net timer runs
    Then the state row has vm_state "extinguishing" and session_ended_at now
    And a VM deallocate is requested by the Function exactly once
    And the webhook receives message "watchdog_boot_failed"
    And a "watchdog/boot_failed" event is recorded

  @unit
  Scenario: Drift: the row says out but the VM is running and the agent is silent
    Given the bonfire is out
    And the VM power state is running
    And last_heartbeat is 25 minutes ago
    When the safety-net timer runs
    Then a VM deallocate is requested by the Function exactly once
    And the webhook receives message "watchdog_heartbeat"

  @unit
  Scenario: Extinguishing with an expired lock and a running VM is finished by the timer
    Given the bonfire is extinguishing with lock_until 1 minute in the past
    And the VM power state is running
    When the safety-net timer runs
    Then a VM deallocate is requested by the Function exactly once
