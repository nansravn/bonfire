Feature: Ignite the bonfire
  Any member of the Discord server starts the game server with one command.
  Messages are quoted by ID from docs/contracts/discord.md.

  Background:
    Given the configured game is "valheim"
    And the adapter declares ready_timeout_minutes 5

  @unit
  Scenario: Ignite from out
    Given the bonfire is out
    When a member runs "/bonfire ignite"
    Then the Function acknowledges within 3 seconds with a deferred channel reply
    And the reply is message "igniting"
    And the state row has vm_state "igniting", a new session_id, session_started_at now, and lock_until 5 minutes ahead
    And a VM start is requested exactly once
    And a "command/ignite" event is recorded with the member as actor and ok true

  @unit
  Scenario: An unregistered subcommand is ignored
    Given the bonfire is out
    When a member runs "/bonfire start"
    Then no VM start is requested
    And the state row has vm_state "out"

  @unit
  Scenario: Ignite while lit only replies with status
    Given the bonfire is lit with 2 players online
    When a member runs "/bonfire ignite"
    Then the reply is message "status_lit" with n 2, h 1, mm 00
    And no VM start is requested
    And the state row is unchanged

  @unit
  Scenario: Ignite while igniting only replies with status
    Given the bonfire is igniting
    When a member runs "/bonfire ignite"
    Then the reply is message "status_igniting" with m 1
    And no VM start is requested

  @unit
  Scenario: Ignite while extinguishing only replies with status
    Given the bonfire is extinguishing
    When a member runs "/bonfire ignite"
    Then the reply is message "status_extinguishing"
    And no VM start is requested

  @unit
  Scenario: The agent marks the bonfire lit when the game is ready
    Given the bonfire is igniting since 90 seconds ago
    And the adapter reports is_ready success
    When the agent runs its check
    Then the state row has vm_state "lit", lock_until null, and last_health "ok"
    And the webhook receives message "ready"
    And a "vm/ready" event is recorded with duration_ms of about 90000

  @unit
  Scenario: The agent keeps waiting while the game is not ready
    Given the bonfire is igniting since 60 seconds ago
    And the adapter reports is_ready not ready
    When the agent runs its check
    Then the state row still has vm_state "igniting"
    And no message is posted

  @unit
  Scenario: Failure to become ready within the deadline
    Given the bonfire is igniting since 5 minutes ago
    And the adapter reports is_ready not ready
    When the agent runs its check
    Then the state row has vm_state "lit", lock_until null, and last_health "crashed"
    And the webhook receives message "ignite_failed"
    And a "vm/ignite_failed" event is recorded with ok false
    And no VM deallocate is requested
