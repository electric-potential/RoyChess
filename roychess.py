"""
this file has been updated on 12/05/2020 at 14:45
"""

from __future__ import unicode_literals
import discord
from discord.ext.commands import Bot
from discord.ext.commands import CommandNotFound
from discord.ext.commands import MemberConverter
import json
import time
import datetime
import asyncio

import chess
import chess.pgn
import io

prefix = 'rc.'
description = 'chess bot'
bot = Bot(command_prefix=prefix, description=description)
token = '' # input your own token here if you have your own testing suite

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

def new_game(id1, id2, dtime, ttime): # make sure you pass in all arguments as strings
    game = chess.pgn.Game()
    game.headers["Event"] = "RoyChess standard match"
    game.headers["Site"] = "RoyChess"
    game.headers["Round"] = "0"
    game.headers["Date"] = dtime
    game.headers["Time"] = ttime
    game.headers["White"] = id1
    game.headers["Black"] = id2
    game.headers["Result"] = ""
    game.headers["Move"] = "None"
    return game

def error_embed(b, t, msg):
    emb = discord.Embed(
                        title = t,
                        description = msg,
                        color = discord.Color.from_rgb(255,0,0)
                        )
    emb.set_footer(text=str(b.me), icon_url=b.me.avatar_url)
    return emb

@bot.event
async def on_ready(): ####################################################################################################################################
    print('logged in') # offload the loop to another function eventually
    print('discord version : '+str(discord.__version__))
    await bot.change_presence(status=discord.Status.online, activity=discord.Game(name=prefix+"commands"))
    bot.me = None # change this to find yourself
    bot.home = None # home server
    bot.saving = False
    bot.chess_emojis = {}
    for emoji in bot.home.emojis: # home server should have all chess piece assets
        bot.chess_emojis[emoji.name] = emoji
    try:
        f = open("games.json", "r")
        bot.games = json.load(f)
        f.close()
    except Exception:
        bot.games = {}
        f = open("games.json", "w")
        f.close()
    try:
        f = open("history.json", "r")
        bot.history = json.load(f)
        f.close()
    except Exception:
        bot.history = {}
        f = open("history.json", "w")
        f.close()
    try:
        f = open("profiles.json", "r")
        bot.profiles = json.load(f)
        f.close()
    except Exception:
        bot.profiles = {}
        f = open("profiles.json", "w")
        f.close()

    while True:
        await asyncio.sleep(600) # every 10 minutes
        to_delete = []
        for i in bot.games.keys():
            game = chess.pgn.read_game(io.StringIO(bot.games[i]))
            if time.time() - float(game.headers["Time"]) >= 86400 and game.headers["Result"] == "": # one day and game not over
                try:
                    mem1 = None
                    mem2 = None
                    last_move = game.headers["Move"]
                    for mem in bot.get_all_members():
                        if str(mem.id) == game.headers["White"]:
                            mem1 = mem
                        if str(mem.id) == game.headers["Black"]:
                            mem2 = mem
                    if mem1 == None or mem2 == None:
                        raise Exception
                    emb = discord.Embed(
                                        title = "game timed out",
                                        description = "game lasted longer than one day, assuming stale and deleting, additional game info attached",
                                        color = discord.Color.from_rgb(255,0,0)
                                        )
                    emb.add_field(
                                  name = "game ID:",
                                  value = i,
                                  inline = False
                                 )
                    emb.add_field(
                                  name = "white:",
                                  value = str(mem1)+"\n"+str(mem1.id),
                                  inline = False
                                 )
                    emb.add_field(
                                  name = "black:",
                                  value = str(mem2)+"\n"+str(mem2.id),
                                  inline = False
                                 )
                    emb.add_field(
                                  name = "start time:",
                                  value = game.headers["Date"],
                                  inline = False
                                 )
                    emb.add_field(
                                  name = "turn:",
                                  value = {0: "white", 1: "black"}[len(list(game.mainline_moves()))%2],
                                  inline = False
                                 )
                    emb.add_field(
                                  name = "last move:",
                                  value = last_move,
                                  inline = False
                                 )
                    emb.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
                    await mem1.send(embed=emb)
                    if mem1.id != mem2.id:
                        await mem2.send(embed=emb)
                except Exception:
                    pass
                to_delete.append(i)
        for i in to_delete:
            del bot.games[i]
        if not bot.saving:
            bot.saving = True
            f = open("games.json", "w")
            json.dump(bot.games, f) # save every 10 minutes just in case bot goes down
            f.close()
            f = open("history.json", "w")
            json.dump(bot.history, f) # save every 10 minutes just in case bot goes down
            f.close()
            f = open("users.json", "w")
            json.dump(bot.profiles, f) # save every 10 minutes just in case bot goes down
            f.close()
            bot.saving = False # comedy comes in threes

@bot.command(pass_context=True)
async def commands(context): ####################################################################################################################################
    emb = discord.Embed(
                        title = "commands",
                        color = discord.Color.from_rgb(127,127,127)
                        )
    emb.add_field(
                  name = prefix+"info",
                  value = "displays general information about the bot",
                  inline = False
                 )
    emb.add_field(
                  name = prefix+"commands",
                  value = "displays this list of commands",
                  inline = False
                 )
    emb.add_field(
                  name = prefix+"invite",
                  value = "shares the invite URL to add RoyChess to other servers",
                  inline = False
                 )
    emb.add_field(
                  name = prefix+"create_game <username, user ID, or mention>",
                  value = "creates a new game between the user that called the command and the user specified",
                  inline = False
                 )
    emb.add_field(
                  name = prefix+"board <game ID>",
                  value = "displays information about a game board with the specified game ID",
                  inline = False
                 )
    emb.add_field(
                  name = prefix+"move <game ID> <UCI string>",
                  value = "makes a move encoded by the specified UCI string on the board specified by the game ID",
                  inline = False
                 )
    emb.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
    try:
        await context.message.channel.send(embed=emb)
    except Exception:
        pass
    return

@bot.command(pass_context=True)
async def invite(context): ####################################################################################################################################
    emb = discord.Embed(
                        title = "invite",
                        description = "[invite link](https://discordapp.com/oauth2/authorize?&client_id="+str(bot.user.id)+"&scope=bot&permissions=0)",
                        color = discord.Color.from_rgb(127,127,127)
                        )
    emb.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
    try:
        await context.message.channel.send(embed=emb)
    except Exception:
        pass

@bot.command(pass_context=True)
async def create_game(context, *args): ####################################################################################################################################
    try:
        err = "insufficient arguments to command"
        if len(args) != 1:
            raise Exception
        err = "users not found"
        mem1 = context.message.author # may not be discord.Member, potentially discord.User
        conv = MemberConverter() # need to instantiate new object, otherwise convert can't pass in self
        mem2 = await conv.convert(context, args[0]) # much cleaner than before, and much more native
        err = "cannot start a game with a bot user"
        if mem1.bot or mem2.bot:
            raise Exception
        for i in bot.games.keys():
            game = chess.pgn.read_game(io.StringIO(bot.games[i]))
            if (str(mem1.id) == game.headers["White"] and str(mem2.id) == game.headers["Black"] and game.headers["Result"] == "") or (str(mem1.id) == game.headers["Black"] and str(mem2.id) == game.headers["White"] and game.headers["Result"] == ""):
                err = "game between users already exists with ID "+i
                raise Exception
        game_id = 1
        while str(game_id) in bot.games.keys() or str(game_id) in bot.history.keys():
            game_id += 1
        game_id = str(game_id)
        dtime = ("0"*(2-len(str(datetime.datetime.now().day))))+str(datetime.datetime.now().day)+"/"+("0"*(2-len(str(datetime.datetime.now().month))))+str(datetime.datetime.now().month)+"/"+str(datetime.datetime.now().year)+" at "+("0"*(2-len(str(datetime.datetime.now().hour))))+str(datetime.datetime.now().hour)+":"+("0"*(2-len(str(datetime.datetime.now().minute))))+str(datetime.datetime.now().minute)+" EST"
        emb = discord.Embed(
                            title = "game created",
                            color = discord.Color.from_rgb(0,255,0)
                            )
        emb.add_field(
                      name = "game ID:",
                      value = game_id,
                      inline = False
                     )
        emb.add_field(
                      name = "white:",
                      value = str(mem1)+"\n"+str(mem1.id),
                      inline = False
                     )
        emb.add_field(
                      name = "black:",
                      value = str(mem2)+"\n"+str(mem2.id),
                      inline = False
                     )
        emb.add_field(
                      name = "start time:",
                      value = dtime,
                      inline = False
                     )
        emb.add_field(
                      name = "turn:",
                      value = "white",
                      inline = False
                     )
        emb.add_field(
                      name = "last move:",
                      value = "None",
                      inline = False
                     )
        emb.add_field(
                      name = "game conclusion:",
                      value = "still in progress",
                      inline = False
                     )
        msg = board_to_string(chess.Board())
        emb.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
        err = "could not contact all players"
        await context.message.channel.send(embed=emb)
        await context.message.channel.send(msg)
        await mem2.send(embed=emb)
        await mem2.send(msg)
        bot.games[game_id] = str(new_game(str(mem1.id), str(mem2.id), dtime, str(time.time())))
    except Exception: # handles embed error messages using previously defined command, cleans control flow up
        try:
            await context.message.channel.send(embed=error_embed(bot, "error creating game", err))
        except Exception:
            pass
    return

@bot.command(pass_context=True)
async def board(context): ####################################################################################################################################
    try:
        err = "insufficient arguments to command"
        if len(context.message.content.split()) != 2: # splitting message content is archaic, switch to argument parsing eventually...
            raise Exception
        game_id = context.message.content.split()[1]
        this_board = chess.Board()
        err = "game ID not found"
        try:
            game = chess.pgn.read_game(io.StringIO(bot.games[game_id]))
        except Exception:
            game = chess.pgn.read_game(io.StringIO(bot.history[game_id]))
        for move in game.mainline_moves():
            this_board.push(move)
        err = "not all players could be found"
        conv = MemberConverter()
        mem1 = await conv.convert(context, game.headers["White"])
        mem2 = await conv.convert(context, game.headers["Black"])
        clr = 254*(1-(len(this_board.move_stack)%2)) # for some reason, discord does'nt like (255,255,255), use (254,254,254) for white instead
        if game.headers["Result"] == "":
            emb = discord.Embed(
                                title = "view board",
                                color = discord.Color.from_rgb(clr,clr,clr)
                                )
        else:
            emb = discord.Embed(
                                title = "view board",
                                color = discord.Color.from_rgb(0,0,255)
                                )
        emb.add_field(
                      name = "game ID:",
                      value = game_id,
                      inline = False
                     )
        emb.add_field(
                      name = "white:",
                      value = str(mem1)+"\n"+str(mem1.id),
                      inline = False
                     )
        emb.add_field(
                      name = "black:",
                      value = str(mem2)+"\n"+str(mem2.id),
                      inline = False
                     )
        emb.add_field(
                      name = "start time:",
                      value = game.headers["Date"],
                      inline = False
                     )
        if game.headers["Result"] == "":
            emb.add_field(
                          name = "turn:",
                          value = {0: "white", 1: "black"}[len(this_board.move_stack)%2],
                          inline = False
                         )
        emb.add_field(
                      name = "last move:",
                      value = game.headers["Move"],
                      inline = False
                     )
        emb.add_field(
                      name = "game conclusion:",
                      value = {"" : "still in progress", "1-0" : "white victory", "0-1" : "black victory", "1/2-1/2" : "draw or stalemate", "r-0" : "white resignation", "0-r" : "black resignation"}[game.headers["Result"]],
                      inline = False
                     )
        emb.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
        msg = board_to_string(this_board)
        err = "could not send message to channel"
        await context.message.channel.send(embed=emb)
        await context.message.channel.send(msg)
    except Exception:
        try:
            await context.message.channel.send(embed=error_embed(bot, "error viewing board", err))
        except Exception:
            pass
    return

@bot.command(pass_context=True)
async def move(context): ####################################################################################################################################
    try:
        err = "insufficient arguments to command"
        if len(context.message.content.split()) != 3:
            raise Exception
        game_id = context.message.content.split()[1]
        err = "this game is already over"
        if game_id in bot.history.keys():
            raise Exception
        this_board = chess.Board()
        err = "game ID not found"
        game = chess.pgn.read_game(io.StringIO(bot.games[game_id]))
        for move in game.mainline_moves():
            this_board.push(move)
        err = "you are not a player in this game"
        if str(context.message.author.id) != game.headers["White"] and str(context.message.author.id) != game.headers["Black"]:
            raise Exception
        err = "this game is already over"
        if game.headers["Result"] != "": # not needed after history implemented
            raise Exception
        err = "it is not your turn"
        if ((len(this_board.move_stack)%2 == 0 and str(context.message.author.id) == game.headers["Black"]) or (len(this_board.move_stack)%2 == 1 and str(context.message.author.id) == game.headers["White"])) and (game.headers["White"] != game.headers["Black"]):
            raise Exception
        err = "not all players could be found"
        conv = MemberConverter()
        mem1 = await conv.convert(context, str(context.message.author.id))
        if str(context.message.author.id) == game.headers["White"]:
            mem2 = await conv.convert(context, game.headers["Black"])
        else:
            mem2 = await conv.convert(context, game.headers["White"])
        if context.message.content.split()[2] == "resign" or context.message.content.split()[2] == "r":
            emb = discord.Embed(
                    title = "move successful, game over",
                    description = "you resigned from the game",
                    color = discord.Color.from_rgb(0,0,255)
                    )
            emb.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
            msg = board_to_string(this_board)
            emb3 = discord.Embed(
                                title = "game over",
                                description = "game ID "+game_id+" ended, your opponent resigned",
                                color = discord.Color.from_rgb(0,0,255)
                                )
            emb3.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
            err = "not all players could be contacted, the move was aborted"
            await context.message.channel.send(embed=emb)
            await context.message.channel.send(msg)
            if str(context.message.author.id) == game.headers["White"]:
                game.headers["Result"] = "r-0"
                game.headers["Move"] = "white resignation"
            else:
                game.headers["Result"] = "0-r"
                game.headers["Move"] = "black resignation"
            bot.games[game_id] = str(game) # push the changes made to the game
            if len(this_board.move_stack) <= 8: # do not save to history if resignation in 8 moves or less!
                del bot.games[game_id]
            else:
                bot.history[game_id] = bot.games[game_id]
                del bot.games[game_id]
            try:
                await mem2.send(embed=emb3)
                await mem2.send(msg)
            except Exception:
                pass
            return
        else:
            err = "invalid UCI string "+context.message.content.split()[2]
            move = chess.Move.from_uci(context.message.content.split()[2])
        if move not in this_board.legal_moves:
            err = "invalid move "+context.message.content.split()[2]
            raise Exception
        this_board.push(move)
        if this_board.is_game_over():
            res = this_board.result().split("-")
            if res[0] == "1/2":
                emb = discord.Embed(
                                    title = "move successful, game over",
                                    description = "the move "+context.message.content.split()[2]+" was made successfully and ended the game in a draw or stalemate",
                                    color = discord.Color.from_rgb(0,0,255)
                                    )
                emb.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
                emb3 = discord.Embed(
                                    title = "game over",
                                    description = "game ID "+game_id+" ended in a draw or stalemate",
                                    color = discord.Color.from_rgb(0,0,255)
                                    )
                emb3.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
            else:
                emb = discord.Embed(
                                    title = "move successful, game over",
                                    description = "the move "+context.message.content.split()[2]+" was made successfully and won you the game",
                                    color = discord.Color.from_rgb(0,0,255)
                                    )
                emb.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
                emb3 = discord.Embed(
                                    title = "game over",
                                    description = "game ID "+game_id+" ended in a loss for you",
                                    color = discord.Color.from_rgb(0,0,255)
                                    )
                emb3.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
        else:
            emb = discord.Embed(
                                title = "move successful",
                                description = "the move "+context.message.content.split()[2]+" was made successfully",
                                color = discord.Color.from_rgb(0,255,0)
                                )
            emb.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
            if this_board.is_check():
                emb3 = discord.Embed(
                                    title = "your turn",
                                    description = "it is your turn to play the board with game ID "+game_id+", you are in check",
                                    color = discord.Color.from_rgb(0,255,0)
                                    )
            else:
                emb3 = discord.Embed(
                                    title = "your turn",
                                    description = "it is your turn to play the board with game ID "+game_id,
                                    color = discord.Color.from_rgb(0,255,0)
                                    )
            emb3.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
        msg = board_to_string(this_board)
        err = "not all players could be contacted, the move was aborted"
        await context.message.channel.send(embed=emb)
        await context.message.channel.send(msg)
        await mem2.send(embed=emb3)
        await mem2.send(msg)
        game.headers["Move"] = context.message.content.split()[2]
        new_game = chess.pgn.Game().from_board(this_board)
        new_game.headers = game.headers
        bot.games[game_id] = str(new_game)
        if this_board.is_game_over():
            new_game["Result"] = this_board.result()
            bot.history[game_id] = str(new_game)
            del bot.games[game_id]
    except Exception:
        try:
            await context.message.channel.send(embed=error_embed(bot, "error making move", err))
        except Exception:
            pass
    return

@bot.command(pass_context=True)
async def info(context): ####################################################################################################################################
    emb = discord.Embed(
                        title = "RoyChess information",
                        color = discord.Color.from_rgb(127,127,127)
                        )
    emb.add_field(
                  name = "bot version:",
                  value = "3", # increment by 1 when pushing a new release
                  inline = True
                 )
    emb.add_field(
                  name = "server count:",
                  value = len(bot.guilds),
                  inline = True
                 )
    emb.add_field(
                  name = "games in progress:",
                  value = len(bot.games),
                  inline = True
                 )
    emb.add_field(
                  name = "games completed:",
                  value = len(bot.history),
                  inline = True
                 )
    emb.add_field(
                  name = "user profiles:",
                  value = len(bot.profiles),
                  inline = True
                 )
    emb.add_field(
                  name = "command prefix:",
                  value = prefix,
                  inline = True
                 )
    emb.add_field(
                  name = "help command:",
                  value = prefix+"commands",
                  inline = True
                 )
    emb.add_field(
                  name = "official RoyChess server:",
                  value = "[link](https://discord.gg/Cj5dmCe)",
                  inline = True
                 )
    emb.set_thumbnail(url=bot.user.avatar_url)
    emb.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
    try:
        await context.message.channel.send(embed=emb)
    except Exception:
        pass
    return

@bot.command(pass_context=True)
async def force_save(context): ####################################################################################################################################
    if context.message.author.id == bot.me.id:
        try:
            if bot.saving:
                raise Exception
            emb = discord.Embed(
                                title = "saved games",
                                description = "saved all games to games.json",
                                color = discord.Color.from_rgb(0,255,0)
                                )
            emb.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
            bot.saving = True
            f = open("games.json", "w")
            json.dump(bot.games, f)
            f.close()
            f = open("history.json", "w")
            json.dump(bot.history, f)
            f.close()
            bot.saving = False
            try:
                await context.message.channel.send(embed=emb)
            except Exception:
                pass
        except Exception:
            emb = discord.Embed(
                                title = "saving error",
                                description = "interrupted while saving",
                                color = discord.Color.from_rgb(255,0,0)
                                )
            emb.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
            try:
                await context.message.channel.send(embed=emb)
            except Exception:
                pass
    else:
        emb = discord.Embed(
                            title = "command error",
                            description = "command does not exist",
                            color = discord.Color.from_rgb(255,0,0)
                            )
        emb.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
        try:
            await context.message.channel.send(embed=emb)
        except Exception:
            pass
        return

@bot.command(pass_context=True)
async def force_delete(context): ####################################################################################################################################
    if context.message.author.id == bot.me.id:
        try:
            if bot.saving:
                raise Exception
            emb = discord.Embed(
                                title = "deleted games",
                                description = "deleted all games being played from games.json",
                                color = discord.Color.from_rgb(0,255,0)
                                )
            emb.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
            bot.games = {}
            bot.history = {}
            bot.saving = True
            f = open("games.json", "w")
            json.dump(bot.games, f)
            f.close()
            f = open("history.json", "w")
            json.dump(bot.history, f)
            f.close()
            bot.saving = False
            try:
                await context.message.channel.send(embed=emb)
            except Exception:
                pass
        except Exception:
            emb = discord.Embed(
                                title = "deleting error",
                                description = "interrupted while saving",
                                color = discord.Color.from_rgb(255,0,0)
                                )
            emb.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
            try:
                await context.message.channel.send(embed=emb)
            except Exception:
                pass
    else:
        emb = discord.Embed(
                            title = "command error",
                            description = "command does not exist",
                            color = discord.Color.from_rgb(255,0,0)
                            )
        emb.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
        try:
            await context.message.channel.send(embed=emb)
        except Exception:
            pass
        return

@bot.event
async def on_command_error(context, error): ####################################################################################################################################
    if isinstance(error, CommandNotFound):
        emb = discord.Embed(
                            title = "command error",
                            description = "command does not exist",
                            color = discord.Color.from_rgb(255,0,0)
                            )
        emb.set_footer(text=str(bot.me), icon_url=bot.me.avatar_url)
        try:
            await context.message.channel.send(embed=emb)
        except Exception:
            pass
        return
    raise error

bot.remove_command("help")
bot.run(token)
