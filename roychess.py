from __future__ import unicode_literals # for handling unicode in messages
import discord
from discord.ext import commands as cmds # command interface
from discord.ext import tasks # for auto-save
from discord.ext.commands import Bot
from discord.ext.commands import CommandNotFound
from discord.ext.commands import MemberConverter
import json # database
import time
import asyncio
import traceback

import setup # local file

import chess
import chess.pgn
import io # reading PGN strings

"""
TODO:

    priority:
        [x] finish docstring for create_game command
        [x] port and refactor info command
        [x] implement accept_invite command
        [x] implement decline_invite command
        [x] implement revoke_invite command
        [x] change "f = open()" statements to "with open() as f" statements
        [x] port and refactor move command
        [x] port and refactor board command
        [x] implement auto-save

    bonus:
        [ ] iron out bugs that may have arisen from refactoring
        [ ] make an embed color chart to organize responses
        [ ] escape markdown on converting member to string
        [ ] possibility to offer draw on your turn
        [ ] remove unused imports
        [ ] implement changelog command
        [ ] implement an owner only force_save command
        [ ] refactor O(n) code in create_game (O(log(n)) is acceptable, maybe binary search?)
        [ ] make multiple different locks to access different games (indexed by the last digit of game ID)
        [ ] turn bot into a cog
        [ ] implement profiles
        [ ] custom chess assets
        [ ] statistics.json file for logging bot usage over time
        [ ] make board_to_string docstring and independent of the global bot variable 
"""

lock = asyncio.Lock()
intents = discord.Intents.default()
intents.members = True
bot = Bot(command_prefix=setup.prefix, description=setup.description, intents=intents)
bot.remove_command("help") # we might define this later

def board_to_string(board):
    natives = {8: "eight", 7: "seven", 6: "six", 5: "five", 4: "four", 3: "three", 2: "two", 1: "one", "a": "regional_indicator_a", "b": "regional_indicator_b", "c": "regional_indicator_c", "d": "regional_indicator_d", "e": "regional_indicator_e", "f": "regional_indicator_f", "g": "regional_indicator_g", "h": "regional_indicator_h"}
    s = str(board).split()
    count = 0
    new = ""
    for piece in s:
        if count % 8 == 0:
            new += ":"+natives[8-(count//8)]+": "
        if piece == ".":
            new_piece = "_"
        else:
            new_piece = piece
        new_piece = str((count + (count//8)) % 2) + new_piece
        new += str(bot.chess_emojis[new_piece])+" "
        if (count + 1) % 8 == 0:
            new += "\n"
        count += 1
    new += str(bot.chess_emojis["blue"])+" "
    for letter in ["a", "b", "c", "d", "e", "f", "g", "h"]:
        new += ":"+natives[letter]+": "
    msg = ""
    for line in new.split("\n"):
        msg += "> "
        for piece in line.split():
            msg += piece
        msg += "\n"
    return msg

def other_embed(title, description, rgb=[255,0,0]):
    if description is not None:
        emb = discord.Embed(
                            title = title,
                            description = description,
                            color = discord.Color.from_rgb(rgb[0],rgb[1],rgb[2])
                            )
    else:
        emb = discord.Embed(
                            title = title,
                            color = discord.Color.from_rgb(rgb[0],rgb[1],rgb[2])
                            )
    emb.set_footer(text=str(bot.owner), icon_url=bot.owner.avatar_url)
    return emb

def error_embed(e):
    return other_embed("Error", discord.utils.escape_markdown(str(type(e).__name__)+": "+str(e)))

async def safe_send_embed(chan, emb, msg=None, file=None):
    try:
        await chan.send(msg, embed=emb, file=file)
        return 0
    except Exception as e:
        return -1

def new_game(id1, id2, ttime): # make sure you pass in all arguments as strings
    game = chess.pgn.Game()
    game.headers["Event"] = "RoyChess match"
    game.headers["Site"] = "RoyChess"
    game.headers["Round"] = "0"
    game.headers["First_Timestamp"] = ttime # string, not float
    game.headers["Last_Timestamp"] = ttime # string, not float
    game.headers["White"] = id1
    game.headers["Black"] = id2
    game.headers["Started"] = "False"
    game.headers["Result"] = ""
    game.headers["Move"] = "None"
    return game

@bot.event
async def on_ready():
    await lock.acquire()
    try:
        info = await bot.application_info() # easier way of getting owner
        bot.owner = info.owner
        bot.home = discord.utils.get(bot.guilds, id=setup.home_id) # home server
        bot.chess_emojis = {}
        for emoji in bot.home.emojis: # home server should have all chess piece assets
            bot.chess_emojis[emoji.name] = emoji
        try:
            with open(setup.games_file, "r") as f:
                bot.games = json.load(f)
            print("games loaded from file")
        except Exception:
            bot.games = {}
            with open(setup.games_file, "w") as f:
                json.dump({}, f)
            print("games failed to load from file")
        try:
            with open(setup.history_file, "r") as f:
                bot.history = json.load(f)
            print("history loaded from file")
        except Exception:
            bot.history = {}
            with open(setup.history_file, "w") as f:
                json.dump({}, f)
            print("history failed to load from file")
        try:
            with open(setup.profiles_file, "r") as f:
                bot.profiles = json.load(f)
            print("profiles loaded from file")
        except Exception:
            bot.profiles = {}
            with open(setup.profiles_file, "w") as f:
                json.dump({}, f)
            print("profiles failed to load from file")
        await bot.change_presence(status=discord.Status.online, activity=discord.Game(name=bot.command_prefix+"commands"))
        print('logged in')
        print('discord version : '+str(discord.__version__))
        print('owner: '+str(bot.owner))
        autosave.start()
    except Exception as e:
        print("something went wrong during initialization, exception printed below")
        traceback.print_exception(type(e), e, e.__traceback__)
    finally:
        lock.release()

@tasks.loop(seconds=setup.autosave)
async def autosave():
    await lock.acquire()
    try:
        now = int(time.time())
        to_delete = []
        for game_id in bot.games:
            game = chess.pgn.read_game(io.StringIO(bot.games[game_id]))
            if now - int(game.headers["First_Timestamp"]) >= setup.timeout and game.headers["Result"] == "": # timeout criterion
                to_delete += [game_id]
                # can't use MemberConverter because task loops have no invocation context (is get_user optimal here?)
                mem1 = bot.get_user(int(game.headers["White"]))
                mem2 = bot.get_user(int(game.headers["Black"]))
                emb = other_embed("Game Timed Out", "The following game has timed out and is being deleted.", [127, 0, 255])
                emb.add_field(
                              name = "Game ID",
                              value = game_id,
                              inline = True
                             )
                emb.add_field(
                              name = "White",
                              value = str(mem1),
                              inline = True
                             )
                emb.add_field(
                              name = "Black",
                              value = str(mem2),
                              inline = True
                             )
                emb.add_field(
                              name = "Invitation Timestamp",
                              value = time.strftime("%A, %B %d, %Y at %H:%M:%S "+setup.timezone, time.localtime(int(game.headers["First_Timestamp"]))),
                              inline = True
                             )
                if game.headers["Started"] == "False":
                    b = None
                    emb.add_field(
                                  name = "Invitation Status",
                                  value = "Pending",
                                  inline = True
                                 )
                else:
                    b = chess.Board()
                    for move in game.mainline_moves():
                        b.push(move)
                    b = board_to_string(b)
                    emb.add_field(
                                  name = "Recent Timestamp",
                                  value = time.strftime("%A, %B %d, %Y at %H:%M:%S "+setup.timezone, time.localtime(int(game.headers["Last_Timestamp"]))),
                                  inline = True
                                  )
                    emb.add_field(
                                  name = "Turn",
                                  value = {0: "White ("+str(mem1)+")", 1: "Black ("+str(mem2)+")"}[len(list(game.mainline_moves()))%2],
                                  inline = True
                                  )
                    emb.add_field(
                                  name = "Last Move",
                                  value = game.headers["Move"],
                                  inline = True
                                 )
                await safe_send_embed(mem1, emb, b)
                await safe_send_embed(mem2, emb, b)
        for game_id in to_delete:
            del bot.games[game_id]
        try:
            with open(setup.games_file, "w") as f:
                json.dump(bot.games, f)
        except Exception:
            print("saving to "+setup.games_file+" failed at "+time.strftime("%A, %B %d, %Y at %H:%M:%S "+setup.timezone, time.localtime(now)))
        try:
            with open(setup.history_file, "w") as f:
                json.dump(bot.games, f)
        except Exception:
            print("saving to "+setup.history_file+" failed at "+time.strftime("%A, %B %d, %Y at %H:%M:%S "+setup.timezone, time.localtime(now)))
        try:
            with open(setup.profiles_file, "w") as f:
                json.dump(bot.games, f)
        except Exception:
            print("saving to "+setup.profiles_file+" failed at "+time.strftime("%A, %B %d, %Y at %H:%M:%S "+setup.timezone, time.localtime(now)))
    except Exception as e:
        traceback.print_exception(type(e), e, e.__traceback__)
    finally:
        lock.release()

# mainline commands below

@bot.command(aliases=[])
async def commands(ctx, *args): # this code can probably be optimized/refactored, but it is not a priority because it is future proof
    try:
        coms = sorted(list(bot.commands), key=lambda x: x.name)
        if ctx.message.author.id != bot.owner.id:
            new_coms = [com for com in coms if not json.loads(com.__doc__)["owner"]]
            coms = new_coms
        if len(args) == 0:
            page_num = 1
        else:
            try:
                page_num = int(args[0])
                if page_num > 1+((len(coms)-1)//10) or page_num < 1:
                    raise Exception
            except Exception:
                await safe_send_embed(ctx.message.channel, other_embed("Error", "Invalid page number."))
                return
        emb = other_embed("Commands (page "+str(page_num)+"/"+str(1+((len(coms)-1)//10))+")",
                          None, [127, 127, 127])
        for com in coms[(page_num-1)*10:page_num*10]:
            try:
                doc = json.loads(com.__doc__)
            except Exception:
                doc = {"name": com.name, "value": "No description provided.", "owner": True}
            emb.add_field(
                name = bot.command_prefix+doc["name"],
                value = (int(doc["owner"])*"__**OWNER ONLY COMMAND.**__\n")+doc["value"],
                inline = False
                )
        await safe_send_embed(ctx.message.channel, emb)
    except Exception:
        pass # disconnected
commands.__doc__ = json.dumps(
    {
        "name": "commands <page number>",
        "value": "Displays this list of commands. Select another page with the optional <page number> argument.",
        "owner": False
        }
    )

@bot.command(aliases=[])
async def invite(ctx):
    try:
        await safe_send_embed(ctx.message.channel, other_embed("Invite", "Use [this link]("+discord.utils.oauth_url(bot.user.id)+") to invite RoyChess to other servers.", [127, 127, 127]))
    except Exception:
        pass
invite.__doc__ = json.dumps(
    {
        "name": "invite",
        "value": "Shares the invite link to add RoyChess to other servers.",
        "owner": False
        }
    )

@bot.command(aliases=[])
async def create_game(ctx, *args):
    await lock.acquire()
    try:
        if len(args) != 1:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "This command requires 1 argument: A player ID or mention of who you are starting a game with."))
            return
        mem1 = ctx.message.author # may not be discord.Member, potentially discord.User
        conv = MemberConverter() # need to instantiate new object, otherwise convert can't pass in self
        try:
            mem2 = await conv.convert(ctx, args[0]) # much cleaner than before, and much more native
        except Exception:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "Player not found, make sure RoyChess shares a server with the other player."))
            return
        # enable game with self temporarily for testing
        """
        if mem1.id == mem2.id:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "You cannot play a game against yourself."))
            return
        """
        if mem1.bot or mem2.bot:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "Bots cannot participate in games."))
            return
        for i in bot.games:
            game = chess.pgn.read_game(io.StringIO(bot.games[i]))
            if (str(mem1.id) == game.headers["White"] and str(mem2.id) == game.headers["Black"]) or (str(mem1.id) == game.headers["Black"] and str(mem2.id) == game.headers["White"]):
                await safe_send_embed(ctx.message.channel, other_embed("Error", "A game with this player already exists with game ID "+str(i)+"."))
                return
        game_id = "1" if len(bot.games) == 0 and len(bot.history) == 0 else str(1 + max([int(x) for x in bot.games] + [int(x) for x in bot.history]))
        # note: a O(n) operation every time a game is created is bad, refactor this
        timestamp = int(time.time())
        emb1 = other_embed("Game Invitation Received", None, [0, 0, 255])
        emb1.add_field(
                       name = "Game ID",
                       value = game_id,
                       inline = True
                      )
        emb1.add_field(
                       name = "White",
                       value = str(mem1),
                       inline = True
                      )
        emb1.add_field(
                       name = "Black",
                       value = str(mem2),
                       inline = True
                      )
        emb1.add_field(
                       name = "Invitation Timestamp",
                       value = time.strftime("%A, %B %d, %Y at %H:%M:%S "+setup.timezone, time.localtime(timestamp)),
                       inline = True
                      )
        emb1.add_field(
                       name = "Invitation Status",
                       value = "Pending",
                       inline = True
                      )
        emb1.add_field(
                       name = "Invitation Help",
                       value = ("You can accept this game invitation with the "
                       "\""+bot.command_prefix+"accept_invite "+game_id+"\" command "
                       "or decline this game invitation with the "
                       "\""+bot.command_prefix+"decline_invite "+game_id+"\" command. "),
                       inline = True
                      )
        if await safe_send_embed(mem2, emb1) < 0:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "Player could not be contacted."))
            return
        emb2 = other_embed("Game Invitation Sent", None, [0, 255, 0])
        emb2.add_field(
                       name = "Game ID",
                       value = game_id,
                       inline = True
                      )
        emb2.add_field(
                       name = "White",
                       value = str(mem1),
                       inline = True
                      )
        emb2.add_field(
                       name = "Black",
                       value = str(mem2),
                       inline = True
                      )
        emb2.add_field(
                       name = "Invitation Timestamp",
                       value = time.strftime("%A, %B %d, %Y at %H:%M:%S "+setup.timezone, time.localtime(timestamp)),
                       inline = True
                      )
        emb2.add_field(
                       name = "Invitation Status",
                       value = "Pending",
                       inline = True
                      )
        emb2.add_field(
                       name = "Invitation Help",
                       value = ("You can revoke this game invitation with the "
                       "\""+bot.command_prefix+"revoke_invite "+game_id+"\" command."),
                       inline = True
                      )
        await safe_send_embed(ctx.message.channel, emb2) # if this fails, follow through with settuping up because the other player was already notified
        bot.games[game_id] = str(new_game(str(mem1.id), str(mem2.id), str(timestamp)))
    except Exception as e:
        await safe_send_embed(ctx.message.channel, error_embed(e))
    finally:
        lock.release()
create_game.__doc__ = json.dumps(
    {
        "name": "create_game <username, user ID, or mention>",
        "value": "Sends an invite for a new game between the user that called the command and the user specified.",
        "owner": False
        }
    )

@bot.command(aliases=[])
async def accept_invite(ctx, *args):
    await lock.acquire()
    try:
        if len(args) != 1:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "This command requires 1 argument: A game ID."))
            return
        mem2 = ctx.message.author # may not be discord.Member, potentially discord.User
        game_id = args[0]
        if game_id not in bot.games:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "A game with the specified ID does not exist."))
            return
        game = chess.pgn.read_game(io.StringIO(bot.games[game_id]))
        if str(mem2.id) != game.headers["Black"]:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "You were not invited to play that game."))
            return
        if game.headers["Started"] == "True":
            await safe_send_embed(ctx.message.channel, other_embed("Error", "You have already accepted the invitation to play this game."))
            return
        conv = MemberConverter() # need to instantiate new object, otherwise convert can't pass in self
        try:
            mem1 = await conv.convert(ctx, game.headers["White"])
        except Exception:
            mem1 = None
        last_timestamp = int(time.time())
        emb = other_embed("Game Invitation Accepted", None, [255, 255, 255])
        emb.add_field(
                      name = "Game ID",
                      value = game_id,
                      inline = True
                      )
        emb.add_field(
                      name = "White",
                      value = str(mem1),
                      inline = True
                      )
        emb.add_field(
                      name = "Black",
                      value = str(mem2),
                      inline = True
                      )
        emb.add_field(
                      name = "Invitation Timestamp",
                      value = time.strftime("%A, %B %d, %Y at %H:%M:%S "+setup.timezone, time.localtime(int(game.headers["First_Timestamp"]))),
                      inline = True
                      )
        emb.add_field(
                      name = "Recent Timestamp",
                      value = time.strftime("%A, %B %d, %Y at %H:%M:%S "+setup.timezone, time.localtime(last_timestamp)),
                      inline = True
                      )
        emb.add_field(
                      name = "Turn",
                      value = "White ("+str(mem1)+")",
                      inline = True
                      )
        emb.add_field(
                      name = "Moves",
                      value = "0",
                      inline = True
                     )
        emb.add_field(
                      name = "Last Move",
                      value = game.headers["Move"],
                      inline = True
                     )
        emb.add_field(
                      name = "Game Conclusion",
                      value = {"" : "Still in Progress", "1-0" : "White Victory", "0-1" : "Black Victory", "1/2-1/2" : "Draw or Stalemate", "r-0" : "White Resignation", "0-r" : "Black Resignation"}[game.headers["Result"]],
                      inline = True
                     )
        b = board_to_string(game.board())
        await safe_send_embed(mem1, emb, b)
        await safe_send_embed(ctx.message.channel, emb, b)
        game.headers["Last_Timestamp"] = str(last_timestamp)
        game.headers["Started"] = "True"
        bot.games[game_id] = str(game)
    except Exception as e:
        await safe_send_embed(ctx.message.channel, error_embed(e))
    finally:
        lock.release()
accept_invite.__doc__ = json.dumps(
    {
        "name": "accept_invite <game ID>",
        "value": "Accepts an invitation to a game.",
        "owner": False
        }
    )

@bot.command(aliases=[])
async def decline_invite(ctx, *args):
    await lock.acquire()
    try:
        if len(args) != 1:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "This command requires 1 argument: A game ID."))
            return
        mem2 = ctx.message.author # may not be discord.Member, potentially discord.User
        game_id = args[0]
        if game_id not in bot.games:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "A game with the specified ID does not exist."))
            return
        game = chess.pgn.read_game(io.StringIO(bot.games[game_id]))
        if str(mem2.id) != game.headers["Black"]:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "You were not invited to play that game."))
            return
        if game.headers["Started"] != "False":
            await safe_send_embed(ctx.message.channel, other_embed("Error", "You have already accepted the invitation to play this game."))
            return
        conv = MemberConverter() # need to instantiate new object, otherwise convert can't pass in self
        try:
            mem1 = await conv.convert(ctx, game.headers["White"])
        except Exception:
            mem1 = None
        last_timestamp = int(time.time())
        emb = other_embed("Game Invitation Declined", None, [127, 0, 255])
        emb.add_field(
                      name = "Game ID",
                      value = game_id,
                      inline = True
                      )
        emb.add_field(
                      name = "White",
                      value = str(mem1),
                      inline = True
                      )
        emb.add_field(
                      name = "Black",
                      value = str(mem2),
                      inline = True
                      )
        emb.add_field(
                      name = "Invitation Timestamp",
                      value = time.strftime("%A, %B %d, %Y at %H:%M:%S "+setup.timezone, time.localtime(int(game.headers["First_Timestamp"]))),
                      inline = True
                      )
        emb.add_field(
                      name = "Recent Timestamp",
                      value = time.strftime("%A, %B %d, %Y at %H:%M:%S "+setup.timezone, time.localtime(last_timestamp)),
                      inline = True
                      )
        await safe_send_embed(mem1, emb)
        await safe_send_embed(ctx.message.channel, emb)
        del bot.games[game_id]
    except Exception as e:
        await safe_send_embed(ctx.message.channel, error_embed(e))
    finally:
        lock.release()
decline_invite.__doc__ = json.dumps(
    {
        "name": "decline_invite <game ID>",
        "value": "Declines an invitation to a game.",
        "owner": False
        }
    )

@bot.command(aliases=[])
async def revoke_invite(ctx, *args):
    await lock.acquire()
    try:
        if len(args) != 1:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "This command requires 1 argument: A game ID."))
            return
        mem1 = ctx.message.author # may not be discord.Member, potentially discord.User
        game_id = args[0]
        if game_id not in bot.games:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "A game with the specified ID does not exist."))
            return
        game = chess.pgn.read_game(io.StringIO(bot.games[game_id]))
        if str(mem1.id) != game.headers["White"]:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "You were not invited to play that game."))
            return
        if game.headers["Started"] != "False":
            await safe_send_embed(ctx.message.channel, other_embed("Error", "You have already accepted the invitation to play this game."))
            return
        conv = MemberConverter() # need to instantiate new object, otherwise convert can't pass in self
        try:
            mem2 = await conv.convert(ctx, game.headers["Black"])
        except Exception:
            mem2 = None
        last_timestamp = int(time.time())
        emb = other_embed("Game Invitation Revoked", None, [127, 0, 255])
        emb.add_field(
                      name = "Game ID",
                      value = game_id,
                      inline = True
                      )
        emb.add_field(
                      name = "White",
                      value = str(mem1),
                      inline = True
                      )
        emb.add_field(
                      name = "Black",
                      value = str(mem2),
                      inline = True
                      )
        emb.add_field(
                      name = "Invitation Timestamp",
                      value = time.strftime("%A, %B %d, %Y at %H:%M:%S "+setup.timezone, time.localtime(int(game.headers["First_Timestamp"]))),
                      inline = True
                      )
        emb.add_field(
                      name = "Recent Timestamp",
                      value = time.strftime("%A, %B %d, %Y at %H:%M:%S "+setup.timezone, time.localtime(last_timestamp)),
                      inline = True
                      )
        await safe_send_embed(mem2, emb)
        await safe_send_embed(ctx.message.channel, emb)
        del bot.games[game_id]
    except Exception as e:
        await safe_send_embed(ctx.message.channel, error_embed(e))
    finally:
        lock.release()
revoke_invite.__doc__ = json.dumps(
    {
        "name": "revoke_invite <game ID>",
        "value": "Revokes an invitation to a game.",
        "owner": False
        }
    )

@bot.command(aliases=[])
async def move(ctx, *args):
    await lock.acquire()
    try:
        if len(args) != 2:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "This command requires 2 arguments: A game ID and a UCI string."))
            return
        game_id = args[0]
        uci_move = args[1]
        if game_id not in bot.games and game_id not in bot.history:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "This game does not exist or was timed out."))
            return
        if game_id not in bot.games:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "This game has already concluded."))
            return
        game = chess.pgn.read_game(io.StringIO(bot.games[game_id]))
        board = chess.Board()
        for move in game.mainline_moves():
            board.push(move)
        if str(ctx.message.author.id) != game.headers["White"] and str(ctx.message.author.id) != game.headers["Black"]:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "You are not a player in this game."))
            return
        if game.headers["Started"] == "False":
            await safe_send_embed(ctx.message.channel, other_embed("Error", "The game invitation has not been accepted yet."))
            return
        if (len(board.move_stack)%2 == 0 and str(ctx.message.author.id) != game.headers["White"]) or (len(board.move_stack)%2 == 1 and str(ctx.message.author.id) != game.headers["Black"]):
            await safe_send_embed(ctx.message.channel, other_embed("Error", "It is not your turn to play in this game."))
            return
        last_timestamp = int(time.time())
        try:
            move = chess.Move.from_uci(uci_move)
        except Exception:
            if uci_move not in ["resign", "forfeit", "quit", "r", "f", "q"]:
                await safe_send_embed(ctx.message.channel, other_embed("Error", "Invalid UCI string."))
                return
            if len(board.move_stack) >= setup.min_move_cutoff:
                game.headers["Last_Timestamp"] = str(last_timestamp)
                if str(ctx.message.author.id) == game.headers["White"]:
                    game.headers["Result"] = "r-0"
                    game.headers["Move"] = "White Resignation"
                else:
                    game.headers["Result"] = "0-r"
                    game.headers["Move"] = "Black Resignation"
                bot.history[game_id] = str(game)
            del bot.games[game_id]
            emb1 = other_embed("Move Successful, Game Over", "You resigned from the game.", [127, 0, 255])
            emb2 = other_embed("Game Over, You Win", "Game ID "+game_id+" ended, your opponent resigned.", [127, 0, 255])
            b = board_to_string(board)
            await safe_send_embed(ctx.message.channel, emb1, b) # it doesn't matter if this send fails
            conv = MemberConverter()
            try:
                mem = await conv.convert(ctx, game.headers["Black"] if str(ctx.message.author.id) == game.headers["White"] else game.headers["White"])
                await safe_send_embed(mem, emb2, b)
            except Exception:
                pass # resignation is still possible even if other member can't be found
            return
        if move not in board.legal_moves:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "Invalid move."))
            return
        conv = MemberConverter() # making a move is not possible if other member can't be found
        try:
            mem = await conv.convert(ctx, game.headers["Black"] if str(ctx.message.author.id) == game.headers["White"] else game.headers["White"])
        except Exception:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "Other player could not be found."))
            return
        board.push(move) # make the move
        b = board_to_string(board)
        if "1/2" in board.result(): # draw
            emb1 = other_embed("Move Successful, Game Over", "The move "+uci_move+" was made successfully and ended the game in a draw or stalemate.", [127, 0, 255])
            emb2 = other_embed("Game Over", "Game ID "+game_id+" ended in a draw or stalemate.", [127, 0, 255])
        elif board.result() != "*": # player who moved won
            emb1 = other_embed("Move Successful, Game Over", "The move "+uci_move+" was made successfully and won you the game.", [127, 0, 255])
            emb2 = other_embed("Game Over", "Game ID "+game_id+" ended in a loss for you.", [127, 0, 255])
        else: # game still going
            emb1 = other_embed("Move Successful", "The move "+uci_move+" was made successfully.", [0, 255, 0])
            emb2 = other_embed("Your Turn", "It is your turn to play the board with game ID "+game_id+{True: ", you are in check.", False: "."}[board.is_check()], [0, 255, 0])
        if await safe_send_embed(mem, emb2, b) < 0:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "Player could not be contacted."))
            return # making a move is impossible if bot can't find other user
        await safe_send_embed(ctx.message.channel, emb1, b)
        new_game = chess.pgn.Game().from_board(board)
        new_game.headers = game.headers
        new_game.headers["Move"] = uci_move
        new_game.headers["Last_Timestamp"] = str(last_timestamp)
        bot.games[game_id] = str(new_game)
        if board.is_game_over():
            new_game.headers["Result"] = board.result()
            bot.history[game_id] = str(new_game)
            del bot.games[game_id]
    except Exception as e:
        await safe_send_embed(ctx.message.channel, error_embed(e))
    finally:
        lock.release()
move.__doc__ = json.dumps(
    {
        "name": "move <game ID> <UCI string or resignation string>",
        "value": "Make a move in a chess game, only [long algebraic notation](https://en.wikipedia.org/wiki/Algebraic_notation_(chess)#Long_algebraic_notation) moves are valid [UCI strings](https://en.wikipedia.org/wiki/Universal_Chess_Interface). You can also forfeit using any of the following UCI strings: resign, forfeit, quit, r, f, or q.",
        "owner": False
        }
    )

@bot.command(aliases=[])
async def board(ctx, *args):
    await lock.acquire()
    try:
        if len(args) != 1:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "This command requires 1 argument: A game ID."))
            return
        game_id = args[0]
        if game_id not in bot.games and game_id not in bot.history:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "This game does not exist or was timed out."))
            return
        game = chess.pgn.read_game(io.StringIO(bot.games[game_id] if game_id in bot.games else bot.history[game_id]))
        conv = MemberConverter()
        try:
            mem1 = await conv.convert(ctx, game.headers["White"])
            mem2 = await conv.convert(ctx, game.headers["Black"])
        except Exception:
            await safe_send_embed(ctx.message.channel, other_embed("Error", "Not all players could be found."))
            return
        board = chess.Board()
        for move in game.mainline_moves():
            board.push(move)
        b = board_to_string(board)
        if game.headers["Started"] == "False": # replace with a ternary expression!
            cl = [0, 0, 255]
        elif game.headers["Result"] == "":
            cl = 3*[255*(1-(len(board.move_stack)%2))]
        else:
            cl = [127, 0, 255]
        emb = other_embed("View Board", None, cl)
        emb.add_field(
                      name = "Game ID",
                      value = game_id,
                      inline = True
                     )
        emb.add_field(
                      name = "White",
                      value = str(mem1),
                      inline = True
                     )
        emb.add_field(
                      name = "Black",
                      value = str(mem2),
                      inline = True
                     )
        emb.add_field(
                      name = "Invitation Timestamp",
                      value = time.strftime("%A, %B %d, %Y at %H:%M:%S "+setup.timezone, time.localtime(int(game.headers["First_Timestamp"]))),
                      inline = True
                     )
        if game.headers["Started"] == "False":
            emb.add_field(
                          name = "Invitation Status",
                          value = "Pending",
                          inline = True
                         )
        else:
            emb.add_field(
                          name = "Recent Timestamp",
                          value = time.strftime("%A, %B %d, %Y at %H:%M:%S "+setup.timezone, time.localtime(int(game.headers["Last_Timestamp"]))),
                          inline = True
                         )
            emb.add_field(
                          name = "Turn",
                          value = {0: "White ("+str(mem1)+")", 1: "Black ("+str(mem2)+")"}[len(board.move_stack)%2],
                          inline = True
                         )
            emb.add_field(
                          name = "Moves",
                          value = str(len(board.move_stack)),
                          inline = True
                         )
            emb.add_field(
                          name = "Last Move",
                          value = game.headers["Move"],
                          inline = True
                         )
            emb.add_field(
                          name = "Game Conclusion",
                          value = {"" : "Still in Progress", "1-0" : "White Victory", "0-1" : "Black Victory", "1/2-1/2" : "Draw or Stalemate", "r-0" : "White Resignation", "0-r" : "Black Resignation"}[game.headers["Result"]],
                          inline = False
                         )
        await safe_send_embed(ctx.message.channel, emb, b)
    except Exception as e:
        await safe_send_embed(ctx.message.channel, error_embed(e))
    finally:
        lock.release()
board.__doc__ = json.dumps(
    {
        "name": "board <game ID>",
        "value": "View the current board of a specific game.",
        "owner": False
        }
    )

@bot.command(aliases=[])
async def info(ctx):
    emb = other_embed("RoyChess information", None, [255, 255, 0])
    emb.add_field(
                  name = "Version",
                  value = "1.00", 
                  inline = True
                 )
    # increment by 1.00 for major feature additions,
    # increment by 0.01 for minor cleanup.
    emb.add_field(
                  name = "Servers",
                  value = len(bot.guilds),
                  inline = True
                 )
    emb.add_field(
                  name = "Games in Progress",
                  value = len(bot.games),
                  inline = True
                 )
    emb.add_field(
                  name = "Games Completed",
                  value = len(bot.history),
                  inline = True
                 )
    # not implemented yet
    """
    emb.add_field(
                  name = "User Profiles:",
                  value = len(bot.profiles),
                  inline = True
                 )
    """
    emb.add_field(
                  name = "Command Prefix",
                  value = bot.command_prefix,
                  inline = True
                 )
    emb.add_field(
                  name = "Help Command",
                  value = bot.command_prefix+"commands", # we might need an actual help command
                  inline = True
                 )
    emb.add_field(
                  name = "Official RoyChess Server",
                  value = "[link]("+setup.home_invite+")",
                  inline = True
                 )
    devs = ""
    if len(setup.developers) == 1:
        devs += setup.developers[0]
    elif len(setup.developers) == 2:
        devs += setup.developers[0] + " and " + setup.developers[1]
    elif len(setup.developers) > 2:
        for i, dev in enumerate(setup.developers):
            if i != len(setup.developers)-1:
                devs += dev + ", "
            else:
                devs += "and " + dev
    emb.add_field(
                  name = "Bot Developers",
                  value = devs,
                  inline = True
                 )
    emb.add_field(
                  name = "Bot Owner",
                  value = str(bot.owner),
                  inline = True
                 )
    await safe_send_embed(ctx.message.channel, emb)
info.__doc__ = json.dumps(
    {
        "name": "info",
        "value": "Displays general information about the bot.",
        "owner": False
        }
    )

# testing, owner only, or unrelated commands below

@bot.command(aliases=[])
@cmds.is_owner()
async def shutdown(ctx, *args):
    await lock.acquire()
    try:
        await safe_send_embed(ctx.message.channel, other_embed("Shutdown", "Acquiring locks, saving data, and shutting down.", [0,0,0]))
        await bot.change_presence(status=discord.Status.invisible, activity=discord.Game(name=""))
    except Exception:
        pass # disconnect
    finally:
        lock.release()
        await bot.logout()
shutdown.__doc__ = json.dumps(
    {
        "name": "shutdown",
        "value": "Forces the bot to acquire all locks, save data to disk, and logs out.",
        "owner": True
        }
    )

@bot.command(aliases=[])
@cmds.is_owner()
async def test(ctx, *args):
    await lock.acquire()
    try:
        await safe_send_embed(ctx.message.channel, other_embed("Game", bot.games[args[0]], [0, 255, 0]))
    except Exception as e:
        await safe_send_embed(ctx.message.channel, error_embed(e))
    finally:
        lock.release()
test.__doc__ = json.dumps(
    {
        "name": "test",
        "value": "Just for personal testing.",
        "owner": True
        }
    )

# typical cleanup below

@bot.event
async def on_disconnect():
    await lock.acquire() # the lock always releases, even if internet goes down
    try:
        try:
            with open(setup.games_file, "w") as f:
                json.dump(bot.games, f)
            print("games saved to file")
        except Exception:
            print("games failed to save to file")
            # don't raise exception, otherwise all saving will terminate
        try:
            with open(setup.history_file, "w") as f:
                json.dump(bot.history, f)
            print("history saved to file")
        except Exception:
            print("history failed to save to file")
        try:
            with open(setup.profiles_file, "w") as f:
                json.dump(bot.profiles, f)
            print("profiles saved to file")
        except Exception:
            print("profiles failed to save to file")
    except Exception:
        pass # everything is wrapped in try-catch anyway
    finally:
        lock.release()

@bot.event
async def on_command_error(ctx, e):
    if isinstance(e, CommandNotFound):
        await safe_send_embed(ctx.message.channel, other_embed("Error", "Command \""+str(discord.utils.escape_markdown(ctx.message.content.split()[0]))+"\" does not exist"))
        return
    raise e

# running code below

try:
    bot.run(setup.token)
except Exception as e:
    traceback.print_exception(type(e), e, e.__traceback__)

        
