#!/bin/python

import discord
import dotenv
import os

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


class TalkQueue(commands.Cog):
  """Provide a voice queue where only one person can talk at a time."""

  def __init__(self):
    super(TalkQueue, self).__init__()
    self.running = False
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

  async def printSend(self, ctx, msg):
    """Print a message and send it to Discord."""
    print(msg)
    await ctx.send(msg)

  async def setActive(self, ctx, member):
    """Set a member to the active talker, unmuting them."""
    if not member.voice:
      print('Member %s is not on voice' % member.display_name)
      return False

    await self.unmute(member)
    self.active = member
    msg = '%s is now  active' % member.mention
    if self.topic:
      msg += ' (topic: %s)' % self.topic
    if self.queue:
      msg += '. %s is next up.' % self.queue[0].mention
    await self.printSend(ctx, msg)
    return True

  def isMod(self, ctx, member=None):
    """Check if a member (or ctx author) is a mod.

    Mods are either the person that started the discussion or
    members of the channel that got permission to manage channel messages.
    """
    if member is None:
      member = ctx.author
    return self.host == member or member.permissions_in(self.text_channel).manage_messages

  def assertIsModAndRunning(self, ctx):
    """Assert the queue is active and in this channel and the author is a mod."""
    self.assertIsRunningChannel(ctx)
    self.assertIsMod(ctx)

  def assertIsMod(self, ctx, member=None):
    """Assert the author is a mod."""
    if not self.isMod(ctx, member):
      raise commands.checkfailure(
          '%s(%s): command may only be used by mods.',
          (ctx.command.name, member.display_name))

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
      print('%s joined voice; mute' % member.display_name)
      await self.mute(member)

  @commands.command(help=HELP_ADD)
  async def add(self, ctx, *args):
    """(mod) Add a member to the back of the queue."""
    self.assertIsModAndRunning(ctx)

    for member in ctx.message.mentions:
      if member not in self.queue:
        self.queue.append(member)

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
      return print('move(): must mention exactly one person.')
    parts = ctx.message.content.split()
    if len(parts) != 3:
      return print('move(): must contain 3 words.')
    if not parts[-1].isnumeric():
      return print('move(): must contain a numeric position.')

    pos = int(parts[-1])
    member = tx.message.mentions[0]

    if member in self.queue:
      del self.queue[self.queue.index(member)]

    self.queue.insert(pos - 1, member)

  @commands.command(help=HELP_TOPIC)
  async def topic(self, ctx, *args):
    """(mod) Set the topic."""
    self.assertIsModAndRunning(ctx)

    self.setTopic(ctx)

  @commands.command(help=HELP_ROUND)
  async def round(self, ctx, *args):
    """(mod) Add everyone to the queue."""
    self.assertIsModAndRunning(ctx)

    for member in self.voice_channel.members:
      if member not in self.queue and self.isMod(ctx, member):
        self.queue.append(member)
    for member in self.voice_channel.members:
      if member not in self.queue:
        self.queue.append(member)

  @commands.command(help=HELP_START)
  async def start(self, ctx, *args):
    """Start a discussion."""
    member = ctx.author
    if self.running:
      print('Cannot start discusion; already running one.')
      return
    if not member.voice:
      await self.printSend(ctx, 'You must be in a voice channel to start a discussion.')
      return

    self.running = True
    self.queue = []
    self.active = None
    self.topic = None
    self.text_channel = ctx.channel
    self.voice_channel = member.voice.channel
    self.host = member

    self.setTopic(ctx)

    print('Starting the discussion. Mute all members.')
    for member in self.voice_channel.members:
      await self.mute(member)

  @commands.command(help=HELP_END)
  async def end(self, ctx, *args):
    """End the discussion."""
    self.assertIsModAndRunning(ctx)

    self.running = False
    print('Ending the discussion. Unmute everyone that I muted.')
    for member in list(self.muted):
      await self.unmute(member)

  @commands.command(help=HELP_JOIN)
  async def join(self, ctx, *args):
    """Join yourself to the queue."""
    self.assertIsRunningChannel(ctx)

    member = ctx.author
    if not self.active:
      print('No active members, set %s active' % member.display_name)
      await self.setActive(ctx, member)
    elif member == self.active:
      msg = '%s is already in the active speaker.' % member.display_name
      await self.printSend(ctx, msg)
    elif member in self.queue:
      msg = '%s is already in the queue (%d/%d).' % (member.display_name, self.queue.index(member) + 1, len(self.queue))
      await self.printSend(ctx, msg)
    else:
      self.queue.append(member)
      await self.printSend(ctx, 'Added: %s (position %d)' % (member.display_name, len(self.queue)))

  @commands.command(help=HELP_LEAVE)
  async def leave(self, ctx, *args):
    """Leave yourself from the queue."""
    self.assertIsRunningChannel(ctx)

    member = ctx.author
    if member not in self.queue:
      return print('leave(): member not in queue')
    del self.queue[self.queue.index(member)]
    self.printSend('Removed %s from the queue.' % member.display_name)

  @commands.command(help=HELP_NEXT)
  async def next(self, ctx, *args):
    """Finish speaking and allow the next speaker."""
    self.assertIsRunningChannel(ctx)

    member = ctx.author
    if not self.active:
      return print('next() but no one is active.')
    if self.active != member and not self.isMod(ctx):
      return await self.printSend(ctx, '%s is not the active speaker' % member.display_name)

    # Mute the active person that just did a !next
    await self.mute(self.active)
    print('next(): mute %s' % self.active.display_name)

    while self.queue:
      if await self.setActive(ctx, self.queue.pop(0)):
        break
    else:
      self.active = None
      await self.printSend(ctx, 'No one left to speak.')

  @commands.command(help=HELP_QUEUE)
  async def queue(self, ctx, *args):
    """Display the queue."""
    self.assertIsRunningChannel(ctx)
    member = ctx.author

    queue = self.queue[:2]
    if ' all' in ctx.message.content:
      queue = self.queue
    m = [n.display_name for n in queue]

    if member in self.queue:
      msg = '%s is %d/%d' % (member.display_name, self.queue.index(member) + 1, len(self.queue))
    else:
      msg = '%s is not in the queue; length: %d' % (member.display_name, len(self.queue))
    await self.printSend(ctx, 'Queue (%s): %s' % (msg, ', '.join(m)))


def main():
  dotenv.load_dotenv()
  bot = commands.Bot(command_prefix='!')
  bot.add_cog(TalkQueue())
  bot.run(os.getenv('DISCORD_TOKEN'))



if __name__ == '__main__':
  main()

# vim:ts=2:sw=2:expandtab
