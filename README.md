# ctfd-time-decay-plugin
Plugin for CTFd which gives full points to the first solver and then computes a time-decay for each subsequent team.

This plugin is similar to [DynamicValueChallenge](https://github.com/CTFd/DynamicValueChallenge). DynamicValueChallenge
retroactively decreases how many points a team received for a challenge based on total number of teams which solved
the challenge. We felt this can create an incentive to create fake accounts and dilute an opponents score.

This plugin gives each team a specific amount of points (based on how much time has elapsed between the first team
who solved the challenge and the current time). We make the game theorists happy by removing any ability to cheat.

Keep in mind that if you change how much a challenge is worth after it has been solved by at least one team, you'll
get incorrect results.

## Install

1. Clone this repository to your CTFd installation under `CTFd/plugins/`.
