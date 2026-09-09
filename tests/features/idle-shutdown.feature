Feature: Agent check: idle shutdown, warnings and health
  The agent runs these rules on every check. An unknown player count never extinguishes.
  The unknown alert threshold is the 60-minute constant in docs/contracts/configuration.md.

  Background:
    Given idle_timeout_minutes is 45
    And idle_warning_minutes is "15,5"
    And idle_check_interval is 1
    And the bonfire is lit

  @unit
  Scenario: The idle timer starts on the first zero-player check
    Given idle_since is null
    And the adapter reports 0 players
    When the agent runs its check at 20:00
    Then idle_since is 20:00
    And warnings_posted is ""
    And no message is posted

  @unit
  Scenario: A player before any warning resets the timer silently
    Given idle_since is 10 minutes ago and warnings_posted is ""
    And the adapter reports 2 players
    When the agent runs its check
    Then idle_since is null
    And no message is posted

  @unit
  Scenario: First warning when 15 minutes remain
    Given idle_since is 30 minutes ago and warnings_posted is ""
    And the adapter reports 0 players
    When the agent runs its check
    Then the webhook receives message "warning" with w 15
    And warnings_posted is "15"
    And a "watchdog/warning" event is recorded with player_count 0

  @unit
  Scenario: A warning is posted once
    Given idle_since is 31 minutes ago and warnings_posted is "15"
    And the adapter reports 0 players
    When the agent runs its check
    Then no message is posted
    And warnings_posted is "15"

  @unit
  Scenario: Second warning when 5 minutes remain
    Given idle_since is 40 minutes ago and warnings_posted is "15"
    And the adapter reports 0 players
    When the agent runs its check
    Then the webhook receives message "warning" with w 5
    And warnings_posted is "15,5"

  @unit
  Scenario: A player joining after a warning cancels auto-extinguish
    Given idle_since is 32 minutes ago and warnings_posted is "15"
    And the adapter reports 1 player
    When the agent runs its check
    Then the webhook receives message "idle_cancelled"
    And idle_since is null and warnings_posted is ""
    And a "watchdog/idle_cancelled" event is recorded with player_count 1

  @unit
  Scenario: Burn out when the timeout is reached
    Given idle_since is 45 minutes ago and warnings_posted is "15,5"
    And the adapter reports 0 players
    When the agent runs its check
    Then the state row has vm_state "extinguishing", session_ended_at now, and lock_until 5 minutes ahead
    And idle_since is null and warnings_posted is ""
    And the webhook receives message "idle_shutdown"
    And a "watchdog/idle_shutdown" event is recorded with player_count 0
    And the adapter "stop" subcommand is invoked before the deallocate
    And a VM deallocate is requested by the agent exactly once

  @unit
  Scenario: Unknown player count never extinguishes
    Given idle_since is 50 minutes ago and warnings_posted is "15,5"
    And the adapter reports "unknown"
    When the agent runs its check
    Then no VM deallocate is requested
    And the state row has vm_state "lit"
    And idle_since is still 50 minutes ago
    And no message is posted

  @unit
  Scenario: A failing player_count is treated as unknown
    Given idle_since is 50 minutes ago
    And the adapter player_count exits non-zero
    When the agent runs its check
    Then no VM deallocate is requested
    And last_player_count is -1

  @unit
  Scenario: Unknown for over an hour raises one alert
    Given unknown_since is 61 minutes ago and unknown_alerted is false
    And the adapter reports "unknown"
    When the agent runs its check
    Then the webhook receives message "unknown_alert"
    And unknown_alerted is true
    And a "watchdog/unknown_alert" event is recorded

  @unit
  Scenario: The unknown alert is not repeated
    Given unknown_since is 90 minutes ago and unknown_alerted is true
    And the adapter reports "unknown"
    When the agent runs its check
    Then no message is posted

  @unit
  Scenario: A known count ends the unknown streak
    Given unknown_since is 30 minutes ago
    And the adapter reports 0 players
    When the agent runs its check
    Then unknown_since is null and unknown_alerted is false

  @unit
  Scenario: The timer survives an agent restart
    Given the state row has idle_since 20 minutes ago and warnings_posted ""
    And the agent process has just started with no memory of earlier checks
    And the adapter reports 0 players
    When the agent runs its check
    Then idle_since is still 20 minutes ago

  @unit
  Scenario: Every check writes a heartbeat
    Given the adapter reports 2 players and health "ok"
    When the agent runs its check at 20:00
    Then last_heartbeat is 20:00, last_player_count is 2, and last_health is "ok"

  @unit
  Scenario: A crash is announced once and the agent does not restart the game
    Given last_health is "ok"
    And the adapter reports health "degraded" and player count "unknown"
    When the agent runs its check
    Then the webhook receives message "crash"
    And a "game/crash" event is recorded
    And the adapter "start" subcommand is not invoked
    And last_health is "degraded"

  @unit
  Scenario: Docker giving up is announced once
    Given last_health is "degraded"
    And the adapter reports health "crashed" and player count "unknown"
    When the agent runs its check
    Then the webhook receives message "crash_gave_up"
    And a "game/crash_gave_up" event is recorded
    And no VM deallocate is requested
