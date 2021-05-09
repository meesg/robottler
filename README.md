# TODO
### General
 - [ ] Make sure userscript runs before other javascript to make sure WebSocket is intercepted (right now it seems like a 50/50 sometimes)
 - [ ] Use a linter and formatter
 - [ ] Split off the communication from the bot logic
 - [ ] Store tiles in graph

### Initial settlements
 - [x] Add a check if we have passed the turn since starting it, so we don't send the message to build the settlement twice (necessary because colonist.io likes to send the turn information twice for some reason)
 - [x] Fix bug where findHighestProducingSpot only counts open settlement spots to calculate the settlement index
 - [x] Place road (random is fine for now)

### Expanding settlements
 - [ ] Check highest producing expansion spot with 2 roads between
 - [ ] Point intitial settlement road towards this spot already
 - [ ] Build towards spot if possible
