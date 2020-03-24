# Discord Discussion Queue bot

A Discord bot to manage voice discussions utilizing a queue.

This bot allows you to run a moderated voice discussion on Discord.
When a discussion is started, all users in the voice channel are put
on mute and need to join the queue to talk. The bot will then unmute
one speaker at a time until they signal that they are done and the
next person can speak.

## Commands

```
TalkQueue:
  start  Start a moderated discussion.
  end    End the moderated discussion.
  join   Join the queue to talk.
  next   Finish talking, letting the next person take over.
  leave  Leave the queue.
  queue  List the next two people in the queue. Or !queue all.

  topic  (mods) Set the topic.
  add    (mods) Add users to the queue.
  remove (mods) Remove users from the queue.
  move   (mods) Move user to a specified position in the queue.
  round  (mods) Put everyone in the queue for a round robin.
```

### Starting the discussion

To start a discussion, you must be connected to a voice channel. In a text
channel, use the `start` command. That will begin a discussion using that
voice channel and that text channel. Commands will only be accepted from that
text channel.

Everyone in the voice channel will be muted. They can join the queue using the
commands in the text channel and will be unmuted when it is their turn to talk.

There are some commands that only "mods" can run. Mods include (1) the person
that started the discussion as well as (2) anyone with "manage channel"
permissions on that text channel.

### Ending the discussion

The `end` command can be used by mods to end the discussion. This will unmute
everyone in the voice channel that got muted.

### Using the queue

Users can `join` and `leave` the queue. When it is their turn, they will get
unmuted and can talk. When they are done talking, the `next` command will
mute them again and move on to the next user. Note mods can use `next` as well
to move the discussion on.

The command `queue [all]` can be used to view the queue.

### The Topic

The topic can be set using `start [topic]` by the person starting the
discussion or during the discussion with the `topic` command.

When a user is unmuted and prompted to speak, the topic (if set) will be
displayed as part of the prompt.

### Queue management (mods)

Mods: the person that started the discussion plus anyone with "manage channel"
permissions in the text channel.

Mods can manage the queue. They can `add <@member> [...]` and
`remove <@member> [...]` to add and remove members from the queue. They can
also `move <@member> <position: int>` to move a member to a specific spot in
the queue.

Mods can also "go around the room" with the `round` command that puts everyone
in the queue. This preserves the current queue, adding to the end of the queue
first the mods then everyone else.

