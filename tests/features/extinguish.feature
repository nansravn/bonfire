Feature: Extinguish the bonfire
  A manual stop goes through the agent so the game saves cleanly.

  @unit
  Scenario: Extinguish with nobody online
    Given the bonfire is lit with 0 players online
    When a member runs "/bonfire extinguish"
    Then the reply is message "extinguished_manual" mentioning the member
    And the state row has vm_state "extinguishing", session_ended_at now, and lock_until 5 minutes ahead
    And no VM deallocate is requested by the Function
    And a "command/extinguish" event is recorded with the member as actor

  @unit
  Scenario: The stop alias behaves like extinguish
    Given the bonfire is lit with 0 players online
    When a member runs "/bonfire stop"
    Then the reply is message "extinguished_manual" mentioning the member
    And the state row has vm_state "extinguishing"

  @unit
  Scenario: The agent performs the clean stop and deallocates
    Given the bonfire is extinguishing
    When the agent runs its check
    Then the adapter "stop" subcommand is invoked before any deallocate
    And a VM deallocate is requested by the agent exactly once

  @unit
  Scenario: Extinguish with players online asks for confirmation
    Given the bonfire is lit with 3 players online
    When a member runs "/bonfire extinguish"
    Then the reply is message "confirm_extinguish" with n 3 and buttons "Extinguish" and "Cancel"
    And the state row is unchanged

  @unit
  Scenario: Confirming extinguish with players online
    Given the bonfire is lit with 3 players online
    And a member has been shown message "confirm_extinguish"
    When that member clicks "Extinguish" within 2 minutes
    Then the message is edited to "extinguished_manual_with_players" with n 3
    And the state row has vm_state "extinguishing"
    And a "command/extinguish" event is recorded with player_count 3

  @unit
  Scenario: Cancelling the confirmation
    Given the bonfire is lit with 3 players online
    And a member has been shown message "confirm_extinguish"
    When that member clicks "Cancel"
    Then the message is edited to "confirm_cancelled"
    And the state row is unchanged

  @unit
  Scenario: Someone else cannot confirm
    Given the bonfire is lit with 3 players online
    And a member has been shown message "confirm_extinguish"
    When a different member clicks "Extinguish"
    Then the different member receives ephemeral message "confirm_not_yours"
    And the state row is unchanged

  @unit
  Scenario: The confirmation expires
    Given the bonfire is lit with 3 players online
    And a member has been shown message "confirm_extinguish" 3 minutes ago
    When that member clicks "Extinguish"
    Then the message is edited to "confirm_expired"
    And the state row is unchanged

  @unit
  Scenario: Extinguish while out only replies with status
    Given the bonfire is out
    When a member runs "/bonfire extinguish"
    Then the reply is message "status_out"
    And the state row is unchanged

  @unit
  Scenario: Extinguish during igniting is refused
    Given the bonfire is igniting
    When a member runs "/bonfire extinguish"
    Then the reply is message "status_igniting" with m 1
    And the state row is unchanged

  @unit
  Scenario: Deallocation completion is recorded as out
    Given the bonfire is extinguishing with session_started_at 3 hours ago and session_ended_at 2 minutes ago
    And hours_this_month is 10.0 for the current month
    And the VM power state is deallocated
    When the safety-net timer runs
    Then the state row has vm_state "out", session fields null, lock_until null
    And hours_this_month is about 12.97
    And a "vm/deallocated" event is recorded

  @unit
  Scenario: Ignite right after a burn-out proceeds once the VM is off
    Given the bonfire is extinguishing with lock_until 3 minutes ahead
    And the VM power state is deallocated
    When a member runs "/bonfire ignite"
    Then the state row passes through vm_state "out" and ends in "igniting"
    And a VM start is requested exactly once
    And the reply is message "igniting"

  @unit
  Scenario: Extinguish with a dead agent is finished by the next handler
    Given the bonfire is extinguishing with lock_until 1 minute in the past
    And the VM power state is running
    When a member runs "/bonfire check"
    Then a VM deallocate is requested by the Function exactly once
    And the reply is message "status_extinguishing"
