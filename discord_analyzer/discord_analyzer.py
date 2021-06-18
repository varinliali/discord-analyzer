#!/usr/bin/env python3

import discord
import json
import re
import emoji
from tabulate import tabulate
from datetime import datetime
import pytz
import tzlocal
from os import get_terminal_size


version = "1.0.2"
scan_version = "1.0"        # Increment these when making changes to
analysis_version = "1.0"    # the structure of scans or analysis


########
# Init #
########

scan = None
analysis = None
update = False
always_show = False
always_reanalyze = False
table_format = "pretty"
time_format = "24h"
repeat_emoji = True
legacy_replies = True
timezone = str(tzlocal.get_localzone())

emoji_re = re.compile(r"(?<=<:)[^:\s]+(?=:\d+>)|" + '|'.join(re.escape(e) for e in emoji.UNICODE_EMOJI['en'].keys()))

user_metrics = ["Messages", "Characters\ntyped", "Characters\nper message", "Emoji\nused", "Top\nemoji", "Reactions", "Top\nreaction", "Top overall\nemoji", "Reactions\nreceived", "Top reaction\nreceived", "Mentions", "Times\nmentioned", "Replies", "Times\nreplied to", "Links", "Attachments", "Top attachment\ntype"]
channel_metrics = ["Messages", "Top message\nsender", "Characters\ntyped", "Top character\ntyper", "Characters\nper message", "Emoji\nused", "Top\nemoji", "Reactions", "Top\nreaction", "Top overall\nemoji", "Mentions", "Top\nmentioner", "Top user\nmentioned", "Replies", "Top\nreplier", "Top\nreplied to", "Links", "Attachments", "Top attachment\ntype", "Top attachment\nsender", "Top link\nsender"]
ranks = ["Message\nsender", "Character\ntyper", "Emoji\nused", "Reaction", "Overall\nemoji", "Mentioner", "Mentioned", "Replier", "Replied\nto", "Link\nsender", "Attachment\nsender", "Attachment\ntype"]
week_days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)


#############
# Functions #
#############

def increment(d, key, increment=1):
    """Increment a value in a dictionary. Add the key to the dictionary if it does not exit yet."""
    if key not in d:
        d[key] = 0
    d[key] += increment

def max_value(d):
    """Return the key in the dictionary that corresponds to the largest value."""
    return max(d, key=lambda e: d[e])

def add_dicts(d1, d2):
    """Return a dictionary with the keys of both dictinaries passed and the sum of their values."""
    d = {}
    for k in list(d1.keys()) + list(d2.keys()):
        d[k] = (d1[k] if k in d1 else 0) + (d2[k] if k in d2 else 0)
    return d

def sort_dict_keys(d, reverse=True):
    """Return a list of the keys in a dictionary ordered by their corresponding values."""
    return sorted(d, key=lambda k: d[k], reverse=reverse)

def filter_dict(d, keys):
    """Return a dictionary with the keys of `d` that are present in `keys`."""
    return dict(filter(lambda k: k[0] in keys, d.items()))

def filter_list(l, indexes):
    """Return the list of the values in `l` corresponding to the indexes in `indexes`."""
    filtered = []
    for k, e in enumerate(l):
        if k in indexes:
            filtered.append(e)
    return filtered

def flatten(l):
    """Return a list containing all the elements and elements in the sublists of `l`."""
    return [e for sublist in l for e in sublist]

def compress_dict(d):
    """Return a dictionary containing the sum of all dictionaries within."""
    res = {}
    for v in d.values():
        res = add_dicts(res, v)
    return res

def select(options, key=None):
    """Display a menu with the options given and return the option selected."""

    for i, o in enumerate(options):
        if key:
            o = key(o)
        print(f"{i})", str(o).replace('\n', ' '))
    
    while True:
        try:
            option = list(options)[int(input("> "))]
            print()
            return option
        except KeyboardInterrupt:
            raise KeyboardInterrupt
        except:
            print("Invalid index")
            pass

def multi_select(options):
    """Display a menu with the options given and return the options selected."""

    for i, o in enumerate(options):
        print(f"{i})", str(o).replace('\n', ' '))
    print("\nSelect options (example: '0, 2-5, 7')")

    indexes = None
    while not indexes:
        index_str = input("> ")
        indexes = set()
        try:
            for i in index_str.split(","):
                if "-" in i:
                    r = list(map(int, i.split("-")))
                    if len(r) != 2:
                        raise TypeError
                    if r[0] > r[1]:
                        r[0], r[1] = r[1], r[0]
                    indexes = indexes.union(set(range(r[0], r[1]+1)))
                else:
                    indexes.add(int(i))
            indexes = indexes.intersection(range(len(options)))
        except:
            print("Invalid index set")
    
    print()
    return list(filter_list(options, indexes))

async def scan_server(server, update=False):
    """Save relevant information from all the messages in the selected channels."""

    global scan

    if not update or not scan:
        scan = {"version": scan_version, "server": {"name": server.name, "id": server.id}, "channels": {}, "roles": {}}

    print("\nSelect a channel:")
    channels = multi_select(server.text_channels)

    for i, channel in enumerate(channels):
        id = str(channel.id)
        if (id) not in scan["channels"]:
            scan["channels"][id] = {"name": channel.name, "last_scanned_message": "", "messages": []}
    
        print("Scanning messages from:", channel.name, f"[{i+1}/{len(channels)}]", " ")

        last = scan["channels"][id]["last_scanned_message"]
        last = datetime.fromisoformat(last) if last else ""
        new_last = last

        now = datetime.now()
        age = now - (last if last else channel.created_at)

        async for message in channel.history(limit=None, oldest_first=False):
            if last and last >= message.created_at:
                break

            print(str(message.created_at)[:-3], f"({round((now - message.created_at)/age * 100, 1)}%)", end="\r")

            if not new_last or message.created_at > new_last:
                new_last = message.created_at

            # Reactions
            reactions = {}
            for r in message.reactions:
                emoji = r.emoji if type(r.emoji) is str else r.emoji.name
                reactions[emoji] = [user.name async for user in r.users()]

            # Replies
            replying_to = ""
            try: replying_to = message.reference.resolved.author.name
            except: pass
            
            # Mentions
            mentions = [user.name for user in message.mentions]
            if replying_to in mentions:
                mentions.remove(replying_to)

            # Content
            content = message.clean_content

            # Attachments
            attachments = []
            if message.attachments:
                for a in message.attachments:
                    if a.content_type:
                        attachments.append(a.content_type.split("/")[0])

            # Links
            links = re.findall(r"https?:\/\/[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b[-a-zA-Z0-9()@:%_\+.~#?&//=]*", content)
            for l in links:
                content = content.replace(l, "")

            scan["channels"][id]["messages"].append({
                "timestamp": str(message.created_at),
                "author": message.author.name,
                "content": re.sub(r"<(:[^:\s]+:)\d+>", r"\1", content),
                "emoji": re.findall(emoji_re, content),
                "reactions": reactions,
                "mentions": mentions,
                "replying_to": replying_to,
                "attachments": attachments,
                "links": links,
            })
        
        scan["channels"][id]["last_scanned_message"] = str(new_last)
        
    
    for r in server.roles:
        scan["roles"][r.name] = [user.name for user in r.members]
    
    await client.close()

def analyze_scan():
    """Read all messages from scan and count relevant metrics."""

    global scan

    users = {}
    channels = {}
    emoji = {}
    server = {"name": scan["server"]["name"], "messages": {}, "chars_typed": {}, "emoji": {}, "reactions": {}, "reactions_received": {}, "mentioned": {}, "mentions": {}, "replied_to": {}, "replies": {}, "attachments": {}, "links": {}, "active_hours": {f"{h}h": 0 for h in range(24)}, "active_days": {week_days[d]: 0 for d in range(7)}}

    def init_user(name):
        if name not in users:
            users[name] = {"messages": 0, "chars_typed": 0, "emoji": {}, "reactions": {}, "reactions_received": {}, "mentioned_by": {}, "mentions": {}, "replied_to_by": {}, "replies": {}, "attachments": {}, "links": 0, "active_hours": {f"{h}h": 0 for h in range(24)}, "active_days": {week_days[d]: 0 for d in range(7)}}
    
    def init_channel(channel):
        if channel not in channels:
            channels[channel] = {"messages": {}, "chars_typed": {}, "emoji": {}, "reactions": {}, "reactions_received": {}, "mentioned": {}, "mentions": {}, "replied_to": {}, "replies": {}, "attachments": {}, "links": {}, "active_hours": {f"{h}h": 0 for h in range(24)}, "active_days": {week_days[d]: 0 for d in range(7)}}
    
    def init_emoji(e):
        if e not in emoji:
            emoji[e] = {"in_message": {}, "reactions_given": {}, "reactions_received": {}}

    for id in scan["channels"]:
        channel = scan["channels"][id]["name"]
        init_channel(channel)

        for message in scan["channels"][id]["messages"]:
            global analysis
            
            author = message["author"]
            init_user(author)

            # Messages and links
            increment(channels[channel]["messages"], author)
            increment(server["messages"], author)
            increment(channels[channel]["chars_typed"], author, len(message["content"]))
            increment(server["chars_typed"], author, len(message["content"]))
            if message["links"]:
                increment(channels[channel]["links"], author, len(message["links"]))
                increment(server["links"], author, len(message["links"]))
            users[author]["messages"] += 1
            users[author]["chars_typed"] += len(message["content"])
            users[author]["links"] += len(message["links"])

            # Emoji
            for e in (message["emoji"] if repeat_emoji else set(message["emoji"])):
                increment(users[author]["emoji"], e)
                increment(channels[channel]["emoji"], e)
                increment(server["emoji"], e)
                init_emoji(e)
                increment(emoji[e]["in_message"], author)
            
            # Reactions
            for e in message["reactions"]:
                init_emoji(e)
                for name in message["reactions"][e]:
                    init_user(name)
                    increment(users[name]["reactions"], e)
                    increment(channels[channel]["reactions"], e)
                    increment(server["reactions"], e)
                    increment(emoji[e]["reactions_given"], name)
                    increment(emoji[e]["reactions_received"], author)
                    increment(users[author]["reactions_received"], e)
            
            # Legacy replies
            mentions = set(message["mentions"])
            replied_to = None
            if legacy_replies and message["mentions"] and not message["replying_to"] and message["content"].startswith("> "):
                for l in message["content"].split("\n"):
                    if l.startswith("> "):
                        for m in message["mentions"]:
                            if re.search(f"(?<!`)@{m}(?!`)", l):
                                pass
                                mentions.remove(m)
                    else: break
                for m in message["mentions"]:
                    if l.startswith(f"@{m}"):
                        replied_to = m
                        if m in mentions:
                            mentions.remove(m)
                        break
                for l in message["content"].split("\n"):
                    if not l.startswith("> "):
                        for m in message["mentions"]:
                            if m != replied_to and re.search(f"(?<!`)@{m}(?!`)", l):
                                mentions.add(m)

            # Mentions
            for name in mentions:
                init_user(name)
                increment(channels[channel]["mentioned"], name)
                increment(server["mentioned"], name)
                increment(users[name]["mentioned_by"], author)
                increment(channels[channel]["mentions"], author)
                increment(server["mentions"], author)
                increment(users[author]["mentions"], name)
            
            # Replies
            name = message["replying_to"] if message["replying_to"] else replied_to
            if name:
                init_user(name)
                increment(channels[channel]["replied_to"], name)
                increment(server["replied_to"], name)
                increment(users[name]["replied_to_by"], author)
                increment(channels[channel]["replies"], author)
                increment(server["replies"], author)
                increment(users[author]["replies"], name)
            
            # Attachments
            for type in message["attachments"]:
                if not author in channels[channel]["attachments"]:
                    channels[channel]["attachments"][author] = {}
                if not author in server["attachments"]:
                    server["attachments"][author] = {}
                increment(channels[channel]["attachments"][author], type)
                increment(server["attachments"][author], type)
                increment(users[author]["attachments"], type)
            
            # Time
            t = datetime.astimezone(pytz.utc.localize(datetime.fromisoformat(message["timestamp"])), pytz.timezone(timezone))
            increment(channels[channel]["active_hours"], f"{t.hour}h")
            increment(server["active_hours"], f"{t.hour}h")
            increment(users[author]["active_hours"], f"{t.hour}h")
            increment(channels[channel]["active_days"], week_days[t.weekday()])
            increment(server["active_days"], week_days[t.weekday()])
            increment(users[author]["active_days"], week_days[t.weekday()])
        
    analysis = {"version": analysis_version, "timezone": timezone, "users": users, "channels": channels, "emoji": emoji, "server": server, "roles": scan["roles"]}

def import_file(path, check_version=None):
    """Return JSON deserialized object read from file. Return false if `OSError` occured."""
    try:
        with open(path, "r") as file:
            obj = json.load(file)
        if check_version and "version" not in obj or obj["version"] != check_version:
            print("Incompatible version")
        else:
            return obj
    except OSError as e:
        print(e)
        return False

def export(obj, filename):
    """Serialize object as JSON and write it to a file."""
    try:
        with open(filename, "w") as file:
            json.dump(obj, file)
    except OSError as e:
        print(e)
    print(f"Exported to '{filename}'")

def reanalyze_prompt():
    """Prompt the user to analyze again if `always_reanalyze` is set to `False`"""
    global always_reanalyze
    if not always_reanalyze:
        print("Note: this setting only takes effect during the analysis process")
    if scan:
        if not always_reanalyze:
            print("Analyze scan again? [yes/no/always]")
            while True:
                ans = input("> ").casefold()
                if not ans: continue
                if ans[0] == "y": break
                if ans[0] == "n": return
                if ans[0] == "a": always_reanalyze = True; break
        print("Analyzing scan...")
        analyze_scan()

def bar_chart(data, sort=False, width=50):
    """Display a horizontal bar chart."""
    label_length = len(max(data.keys(), key=lambda l: len(l)))
    items = sorted(data.items(), key=lambda x: x[1], reverse=True) if sort else data.items()
    for l, v in items:
        size = round(v/max(1, max(data.values())) * width)
        print(f"{l.rjust(label_length, ' ')}: {'▇' * size}{' ' if size else ''}{v}")

def get_users_table(metrics, role_filter):
    """Return a table with a line for each user and a column for each metric."""
    table = []
    users = set(flatten(filter_dict(analysis["roles"], role_filter).values()))
    for u in users:
        info = analysis["users"][u] if u in analysis["users"] else {}
        line = {
            "User": u,
            "Messages": info["messages"] if info else 0,
            "Characters\ntyped": info["chars_typed"] if info else 0,
            "Characters\nper message": round(info["chars_typed"]/info["messages"], 1) if info and info["messages"] > 0 else "-",
            "Emoji\nused": sum(info["emoji"].values()) if info else 0,
            "Top\nemoji": max_value(info["emoji"]) if info and info["emoji"] else "-",
            "Reactions": sum(info["reactions"].values()) if info else 0,
            "Top\nreaction": max_value(info["reactions"]) if info and info["reactions"] else "-",
            "Top overall\nemoji": max_value(add_dicts(info["emoji"], info["reactions"])) if info and (info["emoji"] or info["reactions"]) else "-",
            "Reactions\nreceived": sum(info["reactions_received"].values()) if info else 0,
            "Top reaction\nreceived": max_value(info["reactions_received"]) if info and info["reactions_received"] else "-",
            "Mentions": sum(info["mentions"].values()) if info else 0,
            "Times\nmentioned": sum(info["mentioned_by"].values()) if info else 0,
            "Replies": sum(info["replies"].values()) if info else 0,
            "Times\nreplied to": sum(info["replied_to_by"].values()) if info else 0,
            "Links": info["links"] if info else 0,
            "Attachments": sum(info["attachments"].values()) if info else 0,
            "Top attachment\ntype": max_value(info["attachments"]) if info and info["attachments"] else "-",
        }
        table.append(filter_dict(line, ["User"]+metrics))
    return table

def get_channels_table(metrics):
    """Return a table with a line for each channel and a column for each metric."""
    table = []
    for c in analysis["channels"]:
        info = analysis["channels"][c]
        line = {
            "Channel": c,
            "Messages": sum(info["messages"].values()),
            "Top message\nsender": max_value(info["messages"]) if info["messages"] else "-",
            "Characters\ntyped": sum(info["chars_typed"].values()),
            "Characters\nper message": round(sum(info["chars_typed"].values())/sum(info["messages"].values()), 1) if sum(info["messages"].values()) > 0 else "-",
            "Top character\ntyper": max_value(info["chars_typed"]) if info["chars_typed"] else "-",
            "Emoji\nused": sum(info["emoji"].values()),
            "Top\nemoji": max_value(info["emoji"]) if info["emoji"] else "-",
            "Reactions": sum(info["reactions"].values()),
            "Top\nreaction": max_value(info["reactions"]) if info["reactions"] else "-",
            "Top overall\nemoji": max_value(add_dicts(info["emoji"], info["reactions"])) if (info["emoji"] or info["reactions"]) else "-",
            "Mentions": sum(info["mentions"].values()),
            "Top\nmentioner": max_value(info["mentions"]) if info["mentions"] else "-",
            "Top\nmentioned": max_value(info["mentioned"]) if info["mentioned"] else "-",
            "Replies": sum(info["replies"].values()),
            "Top\nreplier": max_value(info["replies"]) if info["replies"] else "-",
            "Top\nreplied to": max_value(info["replied_to"]) if info["replied_to"] else "-",
            "Links": sum(info["links"].values()),
            "Top link\nsender": max_value(info["links"]) if info["links"] else "-",
            "Attachments": sum([sum(info["attachments"][user].values()) for user in info["attachments"]]),
            "Top attachment\ntype": max_value(compress_dict(info["attachments"])) if info["attachments"] else "-",
            "Top attachment\nsender": max(info["attachments"], key=lambda u: sum(info["attachments"][u].values())) if info["attachments"] else "-",
        }
        table.append(filter_dict(line, ["Channel"]+metrics))
    return table

def show_user_metrics(name):
    """Display specific user metrics."""
    info = analysis["users"][name]
    print("Messages:", info["messages"] if info else 0)
    print("Characters typed:", info["chars_typed"] if info else 0)
    if info and info["messages"]:
        print("Characters per message:", "{:.1f}".format(info["chars_typed"]/info["messages"]))
    print("Emoji used:", sum(info["emoji"].values()) if info else 0)
    print("Reactions:", sum(info["reactions"].values()) if info else 0)
    print("Reactions received:", sum(info["reactions_received"].values()) if info else 0)
    print("Mentions:", sum(info["mentions"].values()) if info else 0)
    print("Times mentioned:", sum(info["mentioned_by"].values()) if info else 0)
    print("Replies:", sum(info["replies"].values()) if info else 0)
    print("Times replied to:", sum(info["replied_to_by"].values()) if info else 0)
    print("Links:", info["links"] if info else 0)
    print("Attachments:", sum(info["attachments"].values()) if info else 0)

def show_metrics(info):
    """Display specific server or channel metrics."""
    print("Messages:", sum(info["messages"].values()))
    print("Characters typed:", sum(info["chars_typed"].values()))
    if info and info["messages"]:
        print("Characters per message:", "{:.1f}".format(sum(info["chars_typed"].values())/sum(info["messages"].values())))
    print("Emoji used:", sum(info["emoji"].values()))
    print("Reactions:", sum(info["reactions"].values()))
    print("Mentions:", sum(info["mentions"].values()))
    print("Replies:", sum(info["replies"].values()))
    print("Links:", sum(info["links"].values()))
    print("Attachments:", sum([sum(info["attachments"][user].values()) for user in info["attachments"]]))

def show_emoji_metrics(info):
    """Display specific emoji metrics."""
    print("Times used in messages:", sum(info["in_message"].values()))
    if info["in_message"]:
        print("Top user in messages:", max_value(info["in_message"]))
    print("Times used as reaction:", sum(info["reactions_given"].values()))
    if info["reactions_given"]:
        print("Top user as reaction:", max_value(info["reactions_given"]))
    if info["reactions_received"]:
        print("Top receiver as reaction:", max_value(info["reactions_received"]))
    print("Times used overall:", sum(info["in_message"].values()) + sum(info["reactions_given"].values()))
    if info["in_message"] or info["reactions_given"]:
        print("Top user overall:", max_value(add_dicts(info["in_message"], info["reactions_given"])))

def get_user_ranks(name):
    """Return a table with a line for each rank and a column for each user rank metric."""
    info = analysis["users"][name]
    table = []
    rows = min(10, max((len(info["emoji"]), len(add_dicts(info["emoji"], info["reactions"])), len(info["reactions_received"]))))
    for i in range(rows):
        table.append({
            "Rank": f"#{i+1}",
            "Emoji\nused": sort_dict_keys(info["emoji"])[i] if len(info["emoji"]) > i else "-",
            "Reaction": sort_dict_keys(info["reactions"])[i] if len(info["reactions"]) > i else "-",
            "Overall\nemoji": sort_dict_keys(add_dicts(info["emoji"], info["reactions"]))[i] if len(add_dicts(info["emoji"], info["reactions"])) > i else "-",
            "Reactions\nreceived": sort_dict_keys(info["reactions_received"])[i] if len(info["reactions_received"]) > i else "-",
            "Mentioned": sort_dict_keys(info["mentions"])[i] if len(info["mentions"]) > i else "-",
            "Mentioned\nby": sort_dict_keys(info["mentioned_by"])[i] if len(info["mentioned_by"]) > i else "-",
            "Replied": sort_dict_keys(info["replies"])[i] if len(info["replies"]) > i else "-",
            "Replied\nto by": sort_dict_keys(info["replied_to_by"])[i] if len(info["replied_to_by"]) > i else "-",
            "Attachment\ntype": sort_dict_keys(info["attachments"])[i] if len(info["attachments"]) > i else "-",
        })
    return table

def get_ranks(info, ranks):
    """Return a table with a line for each rank and a column for each server or channel rank metric."""
    table = []
    rows = min(10, max((len(info["emoji"]), len(add_dicts(info["emoji"], info["reactions"])), len(info["reactions_received"]))))
    for i in range(rows):
        line = {
            "Rank": f"#{i+1}",
            "Message\nsender": sort_dict_keys(info["messages"])[i] if len(info["messages"]) > i else "-",
            "Character\ntyper": sort_dict_keys(info["chars_typed"])[i] if len(info["chars_typed"]) > i else "-",
            "Emoji\nused": sort_dict_keys(info["emoji"])[i] if len(info["emoji"]) > i else "-",
            "Reaction": sort_dict_keys(info["reactions"])[i] if len(info["reactions"]) > i else "-",
            "Overall\nemoji": sort_dict_keys(add_dicts(info["emoji"], info["reactions"]))[i] if len(add_dicts(info["emoji"], info["reactions"])) > i else "-",
            "Mentioner": sort_dict_keys(info["mentions"])[i] if len(info["mentions"]) > i else "-",
            "Mentioned": sort_dict_keys(info["mentioned"])[i] if len(info["mentioned"]) > i else "-",
            "Replier": sort_dict_keys(info["replies"])[i] if len(info["replies"]) > i else "-",
            "Replied\nto": sort_dict_keys(info["replied_to"])[i] if len(info["replied_to"]) > i else "-",
            "Link\nsender": sort_dict_keys(info["links"])[i] if len(info["links"]) > i else "-",
            "Attachment\ntype": sort_dict_keys(compress_dict(info["attachments"]))[i] if len(compress_dict(info["attachments"])) > i else "-",
            "Attachment\nsender": sorted(info["attachments"], key=lambda u: sum(info["attachments"][u].values()), reverse=True)[i] if len(info["attachments"]) > i else "-",
        }
        table.append(filter_dict(line, ["Rank"]+ranks))
    return table

def show_table(table):
    """Display a given table. Prompt the user if the table is to wide for the terminal window and `always_show` is set to `False`"""
    global table_format, always_show
    table_str = tabulate(table, tablefmt=table_format, headers="keys")
    if not always_show and table_str.find("\n") > get_terminal_size()[0]:
        print("The table is too wide for your terminal window.\nPrint anyway? [yes/no/always]")
        while True:
            ans = input("> ").casefold()
            if not ans: continue
            if ans[0] == "y": break
            if ans[0] == "n": return
            if ans[0] == "a": always_show = True; break
    print(table_str)

def show_hours(info, time_format):
    """Display a chart with the amount of messages per hour of the day."""
    print(f"Timezone: {analysis['timezone']}\n")
    active_hours = info["active_hours"]
    if time_format == "12h":
        convert_format = lambda h: datetime.strptime(h.replace("h", ""), "%H").strftime("%-I %p")
        active_hours = {convert_format(h): v for h, v in active_hours.items()}
    bar_chart(active_hours)

def show_days(info):
    """Display a chart with the amount of messages per day of the week."""
    print(f"Timezone: {analysis['timezone']}\n")
    bar_chart(info["active_days"])

def get_emoji_table(rows):
    """Return a table with a line for each ranked emoji and a column for each emoji metric."""
    table = []
    emoji = analysis["emoji"]
    emoji = sorted(emoji, key=lambda e: sum(emoji[e]["in_message"].values()) + sum(emoji[e]["reactions_given"].values()), reverse=True)
    for i, e in enumerate(emoji[:rows]):
        info = analysis["emoji"][e]
        table.append({
            "Rank": f"#{i+1}",
            "Emoji": e,
            "Times used\nin messages": sum(info["in_message"].values()),
            "Top user\nin messages": max_value(info["in_message"]) if info["in_message"] else "-",
            "Times used\nas reaction": sum(info["reactions_given"].values()),
            "Top user\nas reaction": max_value(info["reactions_given"]) if info["reactions_given"] else "-",
            "Top receiver\nas reaction": max_value(info["reactions_received"]) if info["reactions_received"] else "-",
            "Times used\noverall": sum(info["in_message"].values()) + sum(info["reactions_given"].values()),
            "Top user\noverall": max_value(add_dicts(info["in_message"], info["reactions_given"])) if info["in_message"] or info["reactions_given"] else "-",
        })
    return table


##########
# Events #
##########

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    try:
        if update:
            server = client.get_guild(scan["server"]["id"])
        else:
            print("\nSelect a server:")
            server = select(client.guilds, key=lambda s: s.name)
        await scan_server(server, update=update)
        print("Analyzing scan...", " "*16)
        analyze_scan()
    except KeyboardInterrupt:
        await client.close()
        print()


#############
# Main loop #
#############

def main():
    global scan, analysis, update, always_show, always_reanalyze, table_format, time_format, repeat_emoji, legacy_replies, timezone
    
    options = {}
    menu = ["Home"]
    role_filter = ["@everyone"]
    emoji_rows = 20
    
    try:
        while True:
            options = {}

            if menu[-1] != "Back":
                print()
                
            if menu[-1] == "Quit":
                exit(0)
            elif menu[-1] == "About":
                print(f"Discord Analyzer\nVersion: {version} (scan: {scan_version}, analysis: {analysis_version})\n\nhttps://github.com/rodrigohpalmeirim/discord-analyzer")
            elif menu[-1] == "Back":
                menu.pop()
            elif menu[-1] == "Home":
                scan_options = {"u": "Update scan", "e": "Export scan"} if scan else {}
                analysis_options = {"x": "Export analysis", "v": "View analysis"} if analysis else {}
                options = {
                    "n": "New scan",
                    "i": "Import scan",
                    **scan_options,
                    "m": "Import analysis",
                    **analysis_options,
                    "s": "Settings",
                    "a": "About",
                    "q": "Quit"
                }
            elif menu[-1] in ("New scan", "Update scan"):
                update = menu[-1] == "Update scan"
                while not client.user:
                    try:
                        print("Enter your token (see https://github.com/rodrigohpalmeirim/discord-analyzer/wiki/Obtaining-Token)")
                        token = input("> ")
                        client.loop.run_until_complete(client.login(token, bot=False))
                        break
                    except discord.errors.LoginFailure as e:
                        client.clear()
                        client.loop.run_until_complete(client.close())
                        print(e)
                client.clear()
                client.loop.run_until_complete(client.connect()) # will trigger on_ready event and block until connection is closed
            elif menu[-1] == "Import scan":
                print("Enter scan file path")
                new_scan = import_file(input("> "), scan_version)
                if new_scan:
                    scan = new_scan
                    print("Analyzing scan...")
                    analyze_scan()
            elif menu[-1] == "Export scan":
                print("Enter scan name (default: 'scan')")
                filename = input("> ")
                filename = filename + ".json" if filename else "scan.json"
                export(scan, filename)
            elif menu[-1] == "Import analysis":
                print("Enter analysis file path")
                new_analysis = import_file(input("> "), analysis_version)
                if new_analysis:
                    analysis = new_analysis
                    scan = None
            elif menu[-1] == "Export analysis":
                print("Enter analysis name (default: 'analysis')")
                filename = input("> ")
                filename = filename + ".json" if filename else "analysis.json"
                export(analysis, filename)
            elif menu[-1] == "Settings":
                options = {
                    "t": f"Time display format [current: {time_format}]",
                    "a": f"Analysis timezone [current: {timezone}]",
                    "r": f"Count repeated emoji in same message [current: {repeat_emoji}]",
                    "q": f"Count quotes followed by a tag as replies [current: {legacy_replies}]",
                    "b": "Back",
                }
            elif menu[-1].startswith("Time display format"):
                time_format = "12h" if time_format == "24h" else "24h"
            elif menu[-1].startswith("Analysis timezone"):
                timezone = select(pytz.common_timezones)
                reanalyze_prompt()
            elif menu[-1].startswith("Count repeated emoji in same message"):
                repeat_emoji = not repeat_emoji
                reanalyze_prompt()
            elif menu[-1].startswith("Count quotes followed by a tag as replies"):
                legacy_replies = not legacy_replies
                reanalyze_prompt()
            elif menu[-1] == "View analysis":
                print("Server:", analysis["server"]["name"])
                print("Scanned channels:", len(analysis["channels"]), end="\n\n")
                options = {
                    "u": "Users analysis",
                    "e": "Emoji analysis",
                    "c": "Channels analysis",
                    "s": "Server analysis",
                    "b": "Back",
                }
            elif "Users analysis" in menu:
                if menu[-1] == "Users analysis":
                    options = {
                        "m": "Metrics analysis",
                        "s": "Specific user analysis",
                        "b": "Back",
                    }
                    selected_user = None
                elif menu[-1] == "Metrics analysis":
                    print("Current role filter:", ", ".join(role_filter), end="\n\n")
                    options = {
                        "m": "Messages",
                        "e": "Emoji",
                        "r": "Replies and mentions",
                        "l": "Links and attachments",
                        "o": "Overview",
                        "c": "Custom",
                        "s": "Specific metric chart",
                        "f": "Set role filter",
                        "b": "Back",
                    }
                elif menu[-1] == "Messages":
                    show_table(get_users_table(user_metrics[:3], role_filter))
                elif menu[-1] == "Emoji":
                    show_table(get_users_table(user_metrics[3:10], role_filter))
                elif menu[-1] == "Replies and mentions":
                    show_table(get_users_table(user_metrics[10:14], role_filter))
                elif menu[-1] == "Links and attachments":
                    show_table(get_users_table(user_metrics[14:17], role_filter))
                elif menu[-1] == "Overview":
                    metrics = ["Messages", "Characters\nper message", "Top overall\nemoji", "Top reaction\nreceived", "Mentions", "Times\nmentioned", "Replies", "Times\nreplied to", "Links", "Attachments"]
                    show_table(get_users_table(metrics, role_filter))
                elif menu[-1] == "Custom":
                    show_table(get_users_table(multi_select(user_metrics), role_filter))
                elif menu[-1] == "Specific metric chart":
                    metric = select(["Messages", "Characters\ntyped", "Characters\nper message", "Emoji\nused", "Reactions", "Reactions\nreceived", "Mentions", "Times\nmentioned", "Replies", "Times\nreplied to", "Links", "Attachments"])
                    bar_chart({e["User"]: e[metric] for e in get_users_table([metric], role_filter) if e[metric] != "-"}, sort=True)
                elif menu[-1] == "Set role filter":
                    role_filter = multi_select(analysis["roles"])
                elif menu[-1] == "Specific user analysis":
                    if not selected_user:
                        selected_user = select(analysis["users"].keys())
                    print("Selected user:", selected_user, end="\n\n")
                    options = {
                        "m": "Metrics",
                        "r": "Ranks",
                        "h": "Active hours of the day",
                        "d": "Active days of the week",
                        "b": "Back",
                    }
                elif menu[-1] == "Metrics":
                    show_user_metrics(selected_user)
                elif menu[-1] == "Ranks":
                    show_table(get_user_ranks(selected_user))
                elif menu[-1] == "Active hours of the day":
                    show_hours(analysis["users"][selected_user], time_format)
                elif menu[-1] == "Active days of the week":
                    show_days(analysis["users"][selected_user])
            elif "Emoji analysis" in menu:
                if menu[-1] == "Emoji analysis":
                    options = {
                        "r": "Ranks",
                        "s": "Specific emoji analysis",
                        "e": f"Set rank rows [current: {emoji_rows}]",
                        "b": "Back",
                    }
                elif menu[-1] == "Ranks":
                    show_table(get_emoji_table(emoji_rows))
                elif menu[-1] == "Specific emoji analysis":
                    print("Enter an emoji")
                    e = input("> ")
                    print()
                    if e not in analysis["emoji"]:
                        print("Emoji not found")
                    else:
                        show_emoji_metrics(analysis["emoji"][e])
                elif menu[-1].startswith("Set rank rows"):
                    print("Enter number of rows")
                    while True:
                        try:
                            emoji_rows = int(input("> "))
                            break
                        except: pass
            elif "Channels analysis" in menu:
                if menu[-1] == "Channels analysis":
                    options = {
                        "m": "Metrics analysis",
                        "s": "Specific channel analysis",
                        "b": "Back",
                    }
                    selected_channel = None
                elif "Metrics analysis" in menu:
                    if menu[-1] == "Metrics analysis":
                        options = {
                            "m": "Messages",
                            "e": "Emoji",
                            "r": "Replies and mentions",
                            "l": "Links and attachments",
                            "o": "Overview",
                            "c": "Custom",
                            "s": "Specific metric chart",
                            "b": "Back",
                        }
                    elif menu[-1] == "Messages":
                        show_table(get_channels_table(channel_metrics[:5]))
                    elif menu[-1] == "Emoji":
                        show_table(get_channels_table(channel_metrics[5:10]))
                    elif menu[-1] == "Replies and mentions":
                        show_table(get_channels_table(channel_metrics[10:16]))
                    elif menu[-1] == "Links and attachments":
                        show_table(get_channels_table(channel_metrics[16:21]))
                    elif menu[-1] == "Overview":
                        metrics = ["Messages", "Characters\ntyped", "Characters\nper message", "Top overall\nemoji", "Mentions", "Replies", "Links", "Attachments"]
                        show_table(get_channels_table(metrics))
                    elif menu[-1] == "Custom":
                        show_table(get_channels_table(multi_select(channel_metrics)))
                    elif menu[-1] == "Specific metric chart":
                        metric = select(["Messages", "Characters\ntyped", "Characters\nper message", "Emoji\nused", "Reactions", "Mentions", "Replies", "Links", "Attachments"])
                        bar_chart({e["Channel"]: e[metric] for e in get_channels_table([metric]) if e[metric] != "-"}, sort=True)
                elif "Specific channel analysis" in menu:
                    if menu[-1] == "Specific channel analysis":
                        if not selected_channel:
                            selected_channel = select(analysis["channels"].keys())
                        print("Selected channel:", selected_channel, end="\n\n")
                        options = {
                            "m": "Metrics",
                            "r": "Ranks",
                            "h": "Active hours of the day",
                            "d": "Active days of the week",
                            "b": "Back",
                        }
                    elif menu[-1] == "Metrics":
                        show_metrics(analysis["channels"][selected_channel])
                    elif menu[-1] == "Ranks":
                        print("Selected channel:", selected_channel, end="\n\n")
                        options = {
                            "m": "Messages",
                            "e": "Emoji",
                            "r": "Replies and mentions",
                            "l": "Links and attachments",
                            "a": "All",
                            "c": "Custom",
                            "b": "Back",
                        }
                    elif menu[-1] == "Messages":
                        show_table(get_ranks(analysis["channels"][selected_channel], ranks[:2]))
                    elif menu[-1] == "Emoji":
                        show_table(get_ranks(analysis["channels"][selected_channel], ranks[2:5]))
                    elif menu[-1] == "Replies and mentions":
                        show_table(get_ranks(analysis["channels"][selected_channel], ranks[5:9]))
                    elif menu[-1] == "Links and attachments":
                        show_table(get_ranks(analysis["channels"][selected_channel], ranks[9:12]))
                    elif menu[-1] == "All":
                        show_table(get_ranks(analysis["channels"][selected_channel], ranks))
                    elif menu[-1] == "Custom":
                        show_table(get_ranks(analysis["channels"][selected_channel], multi_select(ranks)))
                    elif menu[-1] == "Active hours of the day":
                        show_hours(analysis["channels"][selected_channel], time_format)
                    elif menu[-1] == "Active days of the week":
                        show_days(analysis["channels"][selected_channel])
            elif "Server analysis" in menu:
                if menu[-1] == "Server analysis":
                    options = {
                        "m": "Metrics",
                        "r": "Ranks",
                        "h": "Active hours of the day",
                        "d": "Active days of the week",
                        "b": "Back",
                    }
                elif menu[-1] == "Metrics":
                    show_metrics(analysis["server"])
                elif menu[-1] == "Ranks":
                    options = {
                        "m": "Messages",
                        "e": "Emoji",
                        "r": "Replies and mentions",
                        "l": "Links and attachments",
                        "a": "All",
                        "c": "Custom",
                        "b": "Back",
                    }
                elif menu[-1] == "Messages":
                    show_table(get_ranks(analysis["server"], ranks[:2]))
                elif menu[-1] == "Emoji":
                    show_table(get_ranks(analysis["server"], ranks[2:5]))
                elif menu[-1] == "Replies and mentions":
                    show_table(get_ranks(analysis["server"], ranks[5:9]))
                elif menu[-1] == "Links and attachments":
                    show_table(get_ranks(analysis["server"], ranks[9:12]))
                elif menu[-1] == "All":
                    show_table(get_ranks(analysis["server"], ranks))
                elif menu[-1] == "Custom":
                    show_table(get_ranks(analysis["server"], multi_select(ranks)))
                elif menu[-1] == "Active hours of the day":
                    show_hours(analysis["server"], time_format)
                elif menu[-1] == "Active days of the week":
                    show_days(analysis["server"])

            if not options:
                menu.pop()
                continue
            
            for k, o in options.items():
                print(f"{k}) {o}")
            
            while True:
                i = input("> ")
                if i in options:
                    menu.append(options[i])
                    break

    except KeyboardInterrupt:
        exit(1)


if __name__ == "__main__":
    main()