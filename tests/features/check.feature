Feature: Check the bonfire
  The status reply is posted in channel and chosen by the rules in docs/contracts/discord.md.

  Background:
    Given idle_timeout_minutes is 45

  @unit
  Scenario: Check while out
    Given the bonfire is out
    When a member runs "/bonfire check"
    Then the Function acknowledges with a deferred channel reply
    And the reply is message "status_out"
    And a "command/check" event is recorded

  @unit
  Scenario: Check while igniting
    Given the bonfire is igniting since 1 minute ago
    When a member runs "/bonfire check"
    Then the reply is message "status_igniting" with m 1

  @unit
  Scenario: Check while lit with players
    Given the bonfire is lit with 3 players online, lit for 1 hour 20 minutes
    When a member runs "/bonfire check"
    Then the reply is message "status_lit" with n 3, h 1, mm 20

  @unit
  Scenario: Check while lit with nobody online
    Given the bonfire is lit with 0 players online, lit for 2 hours 5 minutes
    And idle_since is 13 minutes ago
    When a member runs "/bonfire check"
    Then the reply is message "status_lit_idle" with h 2, mm 05, r 32

  @unit
  Scenario: Check while the player count is unknown
    Given the bonfire is lit and the last player count is unknown
    When a member runs "/bonfire check"
    Then the reply is message "status_lit_unknown"

  @unit
  Scenario: Check while the game is down
    Given the bonfire is lit and last_health is "crashed"
    When a member runs "/bonfire check"
    Then the reply is message "status_lit_crashed"

  @unit
  Scenario: Check while extinguishing
    Given the bonfire is extinguishing
    When a member runs "/bonfire check"
    Then the reply is message "status_extinguishing"
