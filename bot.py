#!/bin/python

import discord
import enum
import logging
import os
import sys

from discord.ext import commands

# Help display messages.
HELP_START = """Start a moderated discussion.
You must be in a voice channel which becomes the discussion channel.
The text channel becomes the command channel.
Use !end to end the discussion."""
HELP_END = 'End the moderated discussion.'
HELP_JOIN = 'Join the queue to talk.'
HELP_NEXT = 'Finish talking, letting the next person take over.'
HELP_QUEUE = 'List the next two people in the queue. Or !queue all.'
HELP_LEAVE = 'Leave the queue.'
HELP_ROUND = '(mods) Put everyone in the queue for a round robin.'
HELP_TOPIC = '(mods) Set the topic.'
HELP_ADD = '(mods) Add users to the queue.'
HELP_REMOVE = '(mods) Remove users from the queue.'
HELP_MOVE = '(mods) Move user to a specified position in the queue.'
HELP_OPEN = '(mods) Pause the queue, unmute everyone.'
HELP_PAUSE = '(mods) Pause the queue, unmute mods.'
HELP_RESUME = '(mods) Resume the speaking queue.'


class State(enum.Enum):
  """The state of the discussion."""
  STOPPED = enum.auto()
  RUNNING = enum.auto()
  PAUSED = enum.auto()

  def __bool__(self):
    return self != State.STOPPED


class TalkQueue(commands.Cog):
  """Provide a voice queue where only one person can talk at a time."""

  qualified_name = 'Talk Queue'

  def __init__(self):
    super(TalkQueue, self).__init__()
    self.running = State.STOPPED
    self.muted = set()

  # Helper methods

  async def mute(self, member):
    """Mute a member."""
    if not member.voice or member.voice.mute:
      return
    await member.edit(mute=True)
    self.muted.add(member)

  async def unmute(self, member):
    """Unmute a member."""
    if not member.voice or not member.voice.mute:
      return
    await member.edit(mute=False)
    if member in self.muted:
      self.muted.remove(member)

  def setTopic(self, ctx):
    """Set the topic from a context."""
    msg = ctx.message.content
    if ' ' in msg:
      self.topic = msg[msg.index(' ') + 1:]

  async def send(self, ctx, msg):
    """Send a message to Discord, logging it."""
    logging.info('send(%s)', msg)
    await ctx.send(msg)

  async def addToQueue(self, ctx, member, pos=None):
    if member == self.active:
      msg = '%s is already in the active speaker.' % member.display_name
      await self.send(ctx, msg)
    elif member in self.queue:
      msg = '%s is already in the queue (%d/%d).' % (member.display_name, self.queue.index(member) + 1, len(self.queue))
      await self.send(ctx, msg)
    else:
      if pos is None:
        pos = len(self.queue)
      self.queue.insert(pos, member)
      if self.active:
        await self.send(ctx, 'Added: %s (position %d). %s' % (member.display_name, len(self.queue), self.getQueue()))
      await self.setActive(ctx)

  async def setActive(self, ctx):
    """Set a member to the active talker, unmuting them."""
    if self.active:
      logging.info('setActive(): already got someone active; nothing to do here.')

    while self.queue:
      member = self.queue.pop(0)
      if not member.voice:
        logging.info('setActive(%s): member is not on voice', member.display_name)
        continue
      self.active = member
      await self.unmute(member)

      msg = []
      msg.append('%s is now  active' % member.mention)
      if self.topic:
        msg.append('topic: %s' % self.topic)
      msg.append(self.getQueue())
      await self.send(ctx, ' | '.join(msg))
      return
    else:
      await self.send(ctx, 'There is no one in the queue.')
      return

  def getQueue(self, member=None, full=False):
    """String output of the queue."""
    q = []
    q.append('Queue')
    if self.active:
      q.append('Current speaker: %s' % self.active.display_name)
    else:
      q.append('No active speaker')
    if member:
      if member in self.queue:
        q.append('%s is #%d' % (member.display_name, self.queue.index(member) + 1))
      else:
        q.append('%s is not queued' % member.display_name)
    if full:
      q.append('%d waiting: %s' % (len(self.queue), ', '.join(m.display_name for m in self.queue)))
    else:
      q.append('Next %d of %d: %s' % (min(len(self.queue), 5), len(self.queue), ', '.join(m.display_name for m in self.queue[:5])))
    return ' | '.join(q)

  def isMod(self, member):
    """Check if a member (or ctx author) is a mod.

    Mods are either the person that started the discussion or
    members of the channel that got permission to manage channel messages.
    """
    return self.host == member or member.permissions_in(self.text_channel).manage_messages

  def assertIsModAndRunning(self, ctx):
    """Assert the queue is active and in this channel and the author is a mod."""
    self.assertIsRunningChannel(ctx)
    self.assertIsMod(ctx)

  def assertIsMod(self, ctx, member=None):
    """Assert the author is a mod."""
    if member is None:
      member = ctx.author
    if not self.isMod(member):
      raise commands.checkfailure(
          '%s(%s): command may only be used by mods.',
          (ctx.command.name, member.display_name))

  def assertNotPaused(self, ctx):
    if self.running == State.PAUSED:
      raise commands.CheckFailure(
          '%s(%s): TalkQueue is paused.',
          (ctx.command.name, ctx.author.display_name))

  def assertIsRunningChannel(self, ctx):
    """Assert the queue is active and in this channel."""
    if not self.running:
      raise commands.CheckFailure(
          '%s(%s): TalkQueue not active.',
          (ctx.command.name, ctx.author.display_name))
    if ctx.channel != self.text_channel:
      raise commands.checkfailure(
          '%s(%s): command not used in active channel.',
          (ctx.command.name, ctx.author.display_name))

  @commands.Cog.listener()
  async def on_error(self, event, *args, **kwargs):
    logging.exception('Got an error.', exc_info=True)

  @commands.Cog.listener()
  async def on_voice_state_update(self, member, before, after):
    """Manage server muting on changes.

    If someone enters the discussion channel mid-discussion, mute them.
    If someone enters a channel and there is no discussion happening but
    they are somehow muted (eg got muted and left), unmute them.
    """
    # Ignore unless this is a join.
    if not (before.channel is None and after.channel is not None):
      return

    # Is muted on join
    if after.mute:
      # Discussion is not running or joined a different channel
      if not self.running or after.channel != self.voice_channel:
        await self.unmute(member)

    if self.running and after.channel == self.voice_channel:
      logging.info('%s joined voice; mute', member.display_name)
      await self.mute(member)

  @commands.command(help=HELP_ADD)
  async def add(self, ctx, *args):
    """(mod) Add a member to the back of the queue."""
    self.assertIsModAndRunning(ctx)

    for member in ctx.message.mentions:
      await self.addToQueue(ctx, member)

  @commands.command(help=HELP_REMOVE)
  async def remove(self, ctx, *args):
    """(mod) Remove a member from the queue."""
    self.assertIsModAndRunning(ctx)

    for member in ctx.message.mentions:
      if member in self.queue:
        del self.queue[self.queue.index(member)]

  @commands.command(help=HELP_MOVE)
  async def move(self, ctx, *args):
    """(mod) Move a member to a specific spot in the queue."""
    self.assertIsModAndRunning(ctx)

    if len(ctx.message.mentions) != 1:
      logging.warning('move(%s): must mention exactly one person.', ctx.message.content)
      return
    parts = ctx.message.content.split()
    if len(parts) != 3:
      logging.warning('move(%s): must contain 3 words.', ctx.message.content)
      return
    if not parts[-1].isnumeric():
      logging.warning('move(%s): must contain a numeric position.', ctx.message.content)
      return

    pos = int(parts[-1])
    member = tx.message.mentions[0]

    if member in self.queue:
      del self.queue[self.queue.index(member)]

    await self.addToQueue(ctx, member, pos - 1)

  @commands.command(help=HELP_TOPIC)
  @commands.cooldown(1, 2, commands.BucketType.channel)
  async def topic(self, ctx, *args):
    """(mod) Set the topic."""
    self.assertIsModAndRunning(ctx)

    self.setTopic(ctx)

  @commands.command(help=HELP_ROUND)
  @commands.cooldown(1, 10, commands.BucketType.channel)
  async def round(self, ctx, *args):
    """(mod) Add everyone to the queue."""
    self.assertIsModAndRunning(ctx)

    for member in self.voice_channel.members:
      if member not in self.queue and self.isMod(member):
        self.queue.append(member)
    for member in self.voice_channel.members:
      if member not in self.queue:
        self.queue.append(member)
    await self.setActive(ctx)

  @commands.command(help=HELP_START)
  async def start(self, ctx, *args):
    """Start a discussion."""
    member = ctx.author
    if self.running:
      logging.warning('Cannot start discusion; already running one.')
      return
    if not member.voice:
      await self.send(ctx, 'You must be in a voice channel to start a discussion.')
      return

    self.running = State.RUNNING
    self.queue = []
    self.active = None
    self.topic = None
    self.text_channel = ctx.channel
    self.voice_channel = member.voice.channel
    self.host = member

    self.setTopic(ctx)

    await self.send(ctx, 'Starting the discussion. Mute all members.')
    for member in self.voice_channel.members:
      await self.mute(member)

  @commands.command(help=HELP_END)
  async def end(self, ctx, *args):
    """End the discussion."""
    self.assertIsModAndRunning(ctx)

    self.running = State.STOPPED
    logging.info('Ending the discussion. Unmute everyone that I muted.')
    for member in list(self.muted):
      await self.unmute(member)
    await self.send(ctx, 'The discussion is now closed.')

  @commands.command(help=HELP_JOIN)
  async def join(self, ctx, *args):
    """Join yourself to the queue."""
    self.assertIsRunningChannel(ctx)
    await self.addToQueue(ctx, ctx.author)

  @commands.command(help=HELP_LEAVE)
  async def leave(self, ctx, *args):
    """Leave yourself from the queue."""
    self.assertIsRunningChannel(ctx)

    member = ctx.author
    if member not in self.queue:
      logging.info('leave(%s): member not in queue', member.display_name)
    else:
      del self.queue[self.queue.index(member)]
      self.send('Removed %s from the queue.' % member.display_name)

  @commands.command(help=HELP_NEXT)
  @commands.cooldown(1, 1, commands.BucketType.channel)
  async def next(self, ctx, *args):
    """Finish speaking and allow the next speaker."""
    self.assertIsRunningChannel(ctx)
    if self.running != State.RUNNING:
      logging.info('next(): state %r; do nothing', self.running)
      return

    member = ctx.author
    if not self.active:
      return await self.send(ctx, 'There is no one in the queue.')
    if self.active != member and not self.isMod(ctx.author):
      return await self.send(ctx, '%s is not the active speaker' % member.display_name)

    # Mute the active person that just did a !next
    await self.mute(self.active)
    logging.info('next(): mute %s', self.active.display_name)
    self.active = None

    await self.setActive(ctx)

  @commands.command(help=HELP_QUEUE)
  @commands.cooldown(1, 5, commands.BucketType.channel)
  async def queue(self, ctx, *args):
    """Display the queue."""
    self.assertIsRunningChannel(ctx)

    msg = self.getQueue(ctx.author, ' all' in ctx.message.content)
    await self.send(ctx, msg)

  @commands.command(help=HELP_PAUSE)
  async def pause(self, ctx, *args):
    """(mods) Pause the queue, unmute mods."""
    self.assertIsRunningChannel(ctx)
    self.running = State.PAUSED
    for member in list(self.muted):
      if self.isMod(member):
        await self.unmute(member)
      else:
        await self.mute(member)

  @commands.command(help=HELP_OPEN)
  async def open(self, ctx, *args):
    """(mods) Pause the queue, unmute everyone."""
    self.assertIsRunningChannel(ctx)
    self.running = State.PAUSED
    for member in list(self.muted):
      await self.unmute(member)

  @commands.command(help=HELP_RESUME)
  async def resume(self, ctx, *args):
    """(mods) Resume the speaking queue."""
    self.assertIsRunningChannel(ctx)
    if self.running != State.PAUSED:
      logging.info('resume(): state %r; do nothing', self.running)
      return
    for member in self.voice_channel.members:
      await self.mute(member)
    if self.active:
      a, self.active = self.active, None
      self.addToQueue(ctx, a, 0)
    self.running = State.RUNNING


def main():
  bot = commands.Bot(command_prefix='!')
  bot.add_cog(TalkQueue())
  bot.run(os.getenv('DISCORD_TOKEN'))


if __name__ == '__main__':
  main()

# vim:ts=2:sw=2:expandtab
