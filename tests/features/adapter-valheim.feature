Feature: Valheim adapter conformance
  Instantiates the conformance checklist in docs/contracts/adapter-interface.md for games/valheim.
  Contract scenarios run on any Docker host with the real image; e2e scenarios run on the pilot VM.

  Background:
    Given BONFIRE_GAME is "valheim"
    And BONFIRE_ADAPTER_DIR is the games/valheim directory
    And BONFIRE_DATA_DIR is an empty temporary directory
    And BONFIRE_BACKUP_DIR is an empty temporary directory
    And BONFIRE_STOP_GRACE_SECONDS is 60, copied from adapter.json
    And the valheim server password is provided in the environment

  @contract
  Scenario: adapter.json declares ports and the two tunables
    Given the games/valheim directory
    When adapter.json is parsed
    Then ports contains 2456/udp and 2457/udp
    And stop_grace_seconds is 60 and ready_timeout_minutes is 10

  @contract
  Scenario: install pulls the image
    Given the image is not present locally
    When "adapter.sh install" runs
    Then it exits 0 within 15 minutes
    And the image is present locally

  @contract
  Scenario: start brings the container up
    Given the image is present locally
    When "adapter.sh start" runs
    Then it exits 0 within 2 minutes
    And a container for the adapter is running

  @contract
  Scenario: is_ready reports not ready before the game listens
    Given the container started 5 seconds ago
    When "adapter.sh is_ready" runs
    Then it exits 1 within 10 seconds

  @contract
  Scenario: is_ready reports ready once A2S answers
    Given the container is running and A2S on 127.0.0.1:2457 answers
    When "adapter.sh is_ready" runs
    Then it exits 0 within 10 seconds

  @contract
  Scenario: player_count prints 0 with nobody connected
    Given the game is ready
    When "adapter.sh player_count" runs
    Then it exits 0 and prints exactly "0"

  @contract
  Scenario: player_count prints unknown when the game is unreachable
    Given the container is stopped
    When "adapter.sh player_count" runs
    Then it exits 0 and prints exactly "unknown"

  @contract
  Scenario: health reports ok while running
    Given the game is ready
    When "adapter.sh health" runs
    Then it exits 0 and prints exactly "ok"

  @contract
  Scenario: health reports degraded while Docker restarts the container
    Given the game process was killed and Docker is restarting the container
    When "adapter.sh health" runs
    Then it exits 0 and prints exactly "degraded"

  @contract
  Scenario: health reports crashed when Docker has given up
    Given the container has exited after three failed restarts
    When "adapter.sh health" runs
    Then it exits 0 and prints exactly "crashed"

  @contract
  Scenario: stop saves the world cleanly
    Given the game is ready and a world file exists in BONFIRE_DATA_DIR
    When "adapter.sh stop" runs
    Then it exits 0 within 120 seconds
    And no container for the adapter is running
    And the world file was modified after stop began

  @contract
  Scenario: backup copies the world files
    Given a world file exists in BONFIRE_DATA_DIR
    When "adapter.sh backup" runs
    Then it exits 0 within 5 minutes
    And BONFIRE_BACKUP_DIR contains a copy of every world file

  @contract
  Scenario: Every subcommand writes only its value to stdout
    Given the game is ready
    When each subcommand in the contract runs
    Then stdout contains nothing beyond the value the contract specifies

  @e2e
  Scenario: player_count reflects a real connection
    Given the game is ready on the pilot VM
    When a player connects to BONFIRE_PUBLIC_ADDRESS
    Then "adapter.sh player_count" prints "1" within 60 seconds
    When the player disconnects
    Then "adapter.sh player_count" prints "0" within 60 seconds

  @e2e
  Scenario: A2S answers with crossplay enabled
    Given the compose file enables crossplay
    And the game is ready on the pilot VM
    When "adapter.sh is_ready" and "adapter.sh player_count" run
    Then is_ready exits 0 and player_count prints an integer

  @e2e
  Scenario: Start to ready within the target on the pilot VM
    Given the VM has just booted and the image is present
    When "adapter.sh start" runs and is_ready is polled every 10 seconds
    Then is_ready exits 0 within 3 minutes of start
