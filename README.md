# TODO
### General
 - [ ] Make sure userscript runs before other javascript to make sure WebSocket is intercepted (right now it seems like a 50/50 sometimes)
 - [ ] Use a linter and formatter
 - [ ] Split off the communication from the bot logic
 - [ ] Store tiles in graph and rewrite old functions to use it. (Not quicker, but cleaner because we don't have special cases for z=0 and z=1)

### Initial settlements
 - [x] Add a check if we have passed the turn since starting it, so we don't send the message to build the settlement twice (necessary because colonist.io likes to send the turn information twice for some reason)
 - [x] Fix bug where findHighestProducingSpot only counts open settlement spots to calculate the settlement index
 - [x] Place road (random is fine for now)

### Expanding settlements
 - [x] Check highest producing expansion spot with 2 roads between
 - [x] Point intitial settlement road towards this vertex
 - [x] Build roads towards vertex
 - [x] When all the roads are build, build settlement

### Cities
 - [ ] Upgrade 2 highest producing settlements to cities

### Dev cards
 - [ ] Buy dev cards
 - [ ] Play knight cards whenever possible

### Trading
 - [x] Create function which checks for beneficial trades
 - [x] On opponent turn accept trade if it is beneficial
 - [ ] Check if we have enough cards to trade
 - [ ] On own turn post all beneficial trades
