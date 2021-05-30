from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import logging as lg
import reuters_parser.parser as prs
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sb
import json
import sql.dbManipulator as db
from pandas.plotting import table

import weasyprint as wsp
import PIL as pil


def trim(source_filepath, target_filepath=None, background=None):
    if not target_filepath:
        target_filepath = source_filepath
    img = pil.Image.open(source_filepath)
    if background is None:
        background = img.getpixel((0, 0))
    border = pil.Image.new(img.mode, img.size, background)
    diff = pil.ImageChops.difference(img, border)
    bbox = diff.getbbox()
    img = img.crop(bbox) if bbox else img
    img.save(target_filepath)


def sendTable(df, upd, ctx):
    img_filepath = imgPath("camel", upd, ctx)
    css = wsp.CSS(string='''
    @page { size: 350px 200px; padding: 0px; margin: 0px; }
    table, td, tr, th { border: 1px solid black; }
    td, th { padding: 4px 8px; }
    ''')
    html = wsp.HTML(string=df.to_html(index = False))
    html.write_png(img_filepath, stylesheets=[css])
    trim(img_filepath, img_filepath)
    ctx.bot.send_photo(chat_id = upd.effective_chat.id, photo = open(img_filepath, "rb"))

lg.basicConfig(format='[%(levelname)s]: %(message)s',
                     level=lg.INFO)
plt.switch_backend('Agg')

"""
OWN UTILS
"""

def yearsValues(finData, part, name):
    idx = 0
    for i, x in enumerate(finData[part][0]["rows"]):
        if x["name"] == name:
            idx = i
            break

    data = finData[part][0]["rows"][idx]["data"]

    years, values = [], []

    for row in data:
        yr = row["date"].split('-')[0]
        val = row["value"]
        years.append(int(yr))
        values.append(float(val))
    

    return years, values

def imgPath(name, upd, ctx):
    mid  = upd.message["message_id"]
    chatid = upd.message["chat"]["id"]
    path = "img/plot_%s_%s_%s.png" % (name, chatid, mid)
    return path
    return self.workdir + "/%s%s.png" % (name, str(ctx.user_data["uid"]))

"""
BOT HANDLERS
"""

def showHelp(upd, ctx):
    text = "Commands:\n"
    text += "/fin param RIC\n"
    text += "params: cash, profit, interest, non-interest, assets, equity\n"
    text += "/add - add bank by RIC. Usage: /add RIC\n"
    text += "/find - find RIC of a bank by name. Usage: /find name"
    ctx.bot.send_message(chat_id=upd.effective_chat.id, text = text)

def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!")

def getRIC(update, context):
    args = update.message.text.split()

    if len(args) != 2:
        lg.waring("error")
    else:
        context.bot.send_message(chat_id=update.effective_chat.id, text = args[1])


def getCAMEL(upd, ctx):
    
    context = ctx
    update = upd

    args = upd.message.text.split()

    if len(args) != 2:
        lg.warning("To few argument for /camel command")
        context.bot.send_message(chat_id = update.effective_chat.id, text = "Too few arguments for /camel command (3 required)")
    else:
        RIC = args[1]
        
        # MOO try except here
        infoData, finData, whole = prs.getData(RIC)
        
        mapping = {
            "income" : ("income_annual_tables", "Interest Income, Bank"),
            "profit" : ("income_annual_tables", "Net Income"),
            "n-income" : ("income_annual_tables", "Non-Interest Income, Bank"),
            "assets" : ("balance_sheet_annual_tables", "Total Assets"),
            "cash"   : ("balance_sheet_annual_tables", "Cash & Due from Banks"),
            "loans" : ("balance_sheet_annual_tables", "Net Loans"),
            "equity" : ("balance_sheet_annual_tables", "Total Equity"),
        }

        df = pd.DataFrame(columns = mapping.keys())
        for x in mapping:
            col = x
            part = mapping[x][0]
            name = mapping[x][1]
            years, values = yearsValues(finData, part, name)
            df[col] = pd.Series(values)
            df["year"] = years 
        
        df["C"] = df["equity"] / df["assets"]
        df["A"] = df["loans"] / df["assets"]
        df["M"] = df["income"] / (df["income"] + df["n-income"])
        df["E"] = 0
        df["L"] = df["cash"] / df["assets"]
        for year in df["year"]:
            if year != df["year"].min():
                cur = df.loc[(df["year"] == year), "assets"].iloc[0]
                prev = df.loc[(df["year"] == year - 1), "assets"].iloc[0]
                avg = (cur + prev) * 0.5
                df.loc[(df["year"] == year), "E"] = df.loc[(df["year"] == year), "profit"] / avg
        camel = df.loc[df["year"] > df["year"].min(), ["year", "C", "A", "M", "E", "L"]]
        ctx.bot.send_message(chat_id = upd.effective_chat.id, text = camel.__str__())
        camel.update(camel[["C", "A", "M", "E", "L"]].applymap('{:,.3f}'.format))
        sendTable(camel, upd, ctx)
def getFin(upd, ctx):
    
    context = ctx
    update = upd

    args = upd.message.text.split()

    if len(args) != 3:
        lg.warning("To few argument for /fin command")
        context.bot.send_message(chat_id = update.effective_chat.id, text = "Too few arguments for /fin command (3 required)")
    else:
        command = args[1]
        
        # MOO try except here
        infoData, finData, whole = prs.getData(args[2])
        
        mapping = {
            "income" : ("income_annual_tables", "Interest Income, Bank"),
            "assets" : ("balance_sheet_annual_tables", "Total Assets")
        }

        if command not in mapping:
            lg.warining("Bad command")
            context.bot.send_message(chat_id = update.effective_chat.id, text = "Bad command in /fin")
            return

        part = mapping[command][0]
        name = mapping[command][1]
        
        years, values = yearsValues(finData, part, name)
         
        lg.info(years)
        lg.info(values)
        ax_size = (11.7,8.27)
        
        fig, ax = plt.subplots(figsize = ax_size)
        
        ax.xaxis.set_ticks(years)
        
        lp = sb.lineplot(ax = ax, x = years, y = values)
        
        plt.ticklabel_format(style='plain', axis='y')
       
        path = imgPath("kek", upd, ctx)

        lp.get_figure().savefig(path)
        plt.close(fig)
        
        ctx.bot.send_photo(chat_id = update.effective_chat.id, photo = open(path, "rb"))
        
        #context.bot.send_message(chat_id = update.effective_chat.id, text = infoData["about_info"]["company_name"])
        

        #lg.info("FIN")
        #lg.info(finData)

def displayGraph(upd, ctx, years, values, title, ylabel):
    update = upd
    ax_size = (11.7,8.27)
    fig, ax = plt.subplots(figsize = ax_size)
    ax.xaxis.set_ticks(years)
    lp = sb.lineplot(ax = ax, x = years, y = values)
    plt.ticklabel_format(style='plain', axis='y')
    plt.title(title)
    path = imgPath(ylabel, upd, ctx)
    lp.get_figure().savefig(path)
    plt.close(fig)
    ctx.bot.send_photo(chat_id = update.effective_chat.id, photo = open(path, "rb"))

def getFinBase(upd, ctx):
    args = upd.message.text.split()

    if len(args) != 3:
        lg.warning("...")
        text = ""
        text += "/fin usage:\n"
        text += "/fin param RIC\n"
        text += "params: cash, profit, interest, non-interest, assets, equity\n"
        ctx.bot.send_message(chat_id=upd.effective_chat.id, text = text)

    else:
        commands = {
            "profit" : "net_income",
            "cash" : "cash_and_due_from_banks",
            "loans" : "total_loans",
            "assets" : "total_assets",
            "equity" : "total_equity",
            "interest" : "interes_income",
            "non-interest" : "non_interes_income",

        }
        mapping = {
            "net_income" : "Net Income",
            "cash_and_due_from_banks" : "Cash & Due from banks",
            "total_loans" : "Loans",
            "total_assets" : "Total Assets",
            "total_equity" : "Total Equity",
            "non_interes_income" : "Non-interest income",
            "interes_income" : "Interest income",
        }
        command = args[1]
        RIC = args[2]
        data = db.findBank(RIC)
        
        years = data.loc[:, "year"]

        net_income = data.loc[:, commands[command]]
        
        text = ""
        for i, y in enumerate(years.tolist()):
            text += "%d - %f" % (data.loc[i, "year"], data.loc[i, commands[command]])
            text += "\n"
        
        ctx.bot.send_message(chat_id=upd.effective_chat.id, text = text)
        
        displayGraph(upd, ctx, years, net_income, mapping[commands[command]], "data")


def addRIC(upd, ctx):
    args = upd.message.text.split()
    if len(args) != 2:
        lg.warning("...")
    else:
        RIC = args[1]
        infoData, finData, whole = prs.getData(RIC)
        
        extr = [
            ("balance_sheet_annual_tables", "Cash & Due from Banks", "cash_and_due_from_banks", []),
            ("income_annual_tables", "Interest Income, Bank", "interest_income", []),
            ("income_annual_tables", "Non-Interest Income, Bank", "non_interest_income", []),
            ("balance_sheet_annual_tables", "Other Earning Assets, Total", "other_earning_assets", []),
            ("balance_sheet_annual_tables", "Total Assets", "total_assets", []),
            ("balance_sheet_annual_tables", "Total Deposits", "total_deposits", []),
            ("balance_sheet_annual_tables", "Total Equity", "total_equity", []),
            ("balance_sheet_annual_tables", "Total Interest Expense", "total_interest_expense", []),
            ("balance_sheet_annual_tables", "Net Loans", "net_loans", []),
            ("income_annual_tables", "Net Income", "net_interest_income", []),
        ]
        
        company = infoData["about_info"]["company_name"]
        currency = infoData["keystats"]["revenue"]["currency"]
        country = infoData["about_info"]["country"]

        lg.info((company, currency))

        years, _ = yearsValues(finData, extr[0][0], extr[0][1])

        for x in extr:
            years, values = yearsValues(finData, x[0], x[1])
            for i, y in enumerate(values):
                x[3].append((y, years[i]))
        
        cols = []

        for x in extr:
            cols.append(x[0])

        for i, year in enumerate(years):
            lg.info("===")
            rows = []
            columns = []
            
            for j, e in enumerate(extr):
                rows.append(e[3][i][0])
                columns.append(e[2])
            
            rows.append(year)
            columns.append("year")
            
            rows.append(currency)
            columns.append("currency")
            
            rows.append(company)
            columns.append("bank_name")
            
            rows.append(country)
            columns.append("country")

            df = pd.DataFrame([rows], columns=columns)
            db.addBank(RIC, df)
            lg.info((df["year"], company))

def findByName(upd, ctx):
    args = upd.message.text.split()
    print(args)

    if len(args) != 2:
        lg.warning("...")
    else:
        print("wow")
        name = args[1]
        bank_RICs = db.findRICByName(name)
        text = "Results:\n"
        for x in bank_RICs:
            text += "%s - %s\n" % (x[1], x[0])
            lg.info(x)
        ctx.bot.send_message(chat_id=upd.effective_chat.id, text = text)
        

def echo(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)

upd = Updater(token='1879217464:AAH2M1ORIC-u_2sNtWpxUxbaKlWnLVeNmmc', use_context=True)
updater = upd

disp = upd.dispatcher
dispatcher = disp

start_handler = CommandHandler('start', showHelp)
dispatcher.add_handler(start_handler)

ric_handler = CommandHandler('ric', getRIC)
dispatcher.add_handler(ric_handler)

fin_handler = CommandHandler('fin', getFinBase)
dispatcher.add_handler(fin_handler)

add_handler = CommandHandler('add', addRIC)
dispatcher.add_handler(add_handler)

find_handler = CommandHandler('find', findByName)
dispatcher.add_handler(find_handler)

camel_handler = CommandHandler('camel', getCAMEL)
dispatcher.add_handler(camel_handler)

test_handler = CommandHandler('test', getCAMEL)
dispatcher.add_handler(test_handler)

echo_handler = MessageHandler(Filters.text & (~Filters.command), echo)
dispatcher.add_handler(echo_handler)

updater.start_polling()

print(disp)
