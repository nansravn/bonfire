Feature: Concurrent commands and lock expiry
  A lock in the state row makes transitions exclusive for 5 minutes; expired locks are reconciled.

  @unit
  Scenario: Two ignites at once start the VM once
    Given the bonfire is out
    When member A and member B run "/bonfire ignite" at the same time
    Then exactly one conditional write to the state row succeeds
    And the member whose write succeeded receives message "igniting"
    And the other member receives message "status_igniting"
    And a VM start is requested exactly once

  @unit
  Scenario: A stale ETag is never overwritten
    Given the bonfire is out
    And another writer changes the state row between a handler's read and write
    When the handler writes with the ETag it read
    Then the write fails with a precondition error
    And the handler re-reads the row before deciding what to do

  @unit
  Scenario: An expired lock with a deallocated VM is reconciled to out and ignite proceeds
    Given the bonfire is igniting with lock_until 1 minute in the past
    And the VM power state is deallocated
    When a member runs "/bonfire ignite"
    Then the state row passes through vm_state "out" and ends in "igniting"
    And a VM start is requested exactly once
    And the reply is message "igniting"

  @unit
  Scenario: An expired lock with a running VM and a fresh heartbeat is reconciled to lit
    Given the bonfire is igniting with lock_until 1 minute in the past
    And the VM power state is running
    And last_heartbeat is 1 minute ago
    When a member runs "/bonfire check"
    Then the state row has vm_state "lit" and lock_until null
    And the reply is a status message for state "lit"

  @unit
  Scenario: An active lock blocks state changes while the VM is still running
    Given the bonfire is extinguishing with lock_until 3 minutes ahead
    And the VM power state is running
    When a member runs "/bonfire ignite"
    Then the reply is message "status_extinguishing"
    And the state row is unchanged

  @unit
  Scenario: Extinguish during igniting is refused by the lock
    Given the bonfire is igniting with lock_until 3 minutes ahead
    When a member runs "/bonfire extinguish"
    Then the reply is message "status_igniting"
    And the state row is unchanged
