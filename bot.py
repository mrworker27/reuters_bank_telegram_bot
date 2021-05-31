from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import logging as lg
import reuters_parser.parser as prs
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sb
import json
import sql.dbManipulator as db
from pandas.plotting import table
from countryParser import getGDP, getPopul, getDebt
from exchange import getRate
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


def getCAMELBase(upd, ctx):
    
    context = ctx
    update = upd

    args = upd.message.text.split()

    if len(args) != 2:
        lg.warning("To few argument for /camel command")
        context.bot.send_message(chat_id = update.effective_chat.id, text = "Too few arguments for /camel command (3 required)")
    else:
        RIC = args[1]
        
        df = db.findBank(RIC)

        df["C"] = df["total_equity"] / df["total_assets"]
        df["A"] = df["net_loans"] / df["total_assets"]
        df["M"] = df["interest_income"] / (df["interest_income"] + df["non_interest_income"])
        df["E"] = 0
        df["L"] = df["cash_and_due_from_banks"] / df["total_assets"]
        for year in df["year"]:
            if year != df["year"].min():
                cur = df.loc[(df["year"] == year), "total_assets"].iloc[0]
                prev = df.loc[(df["year"] == year - 1), "total_assets"].iloc[0]
                avg = (cur + prev) * 0.5
                df.loc[(df["year"] == year), "E"] = df.loc[(df["year"] == year), "net_income"] / avg
        camel = df.loc[df["year"] > df["year"].min(), ["year", "C", "A", "M", "E", "L"]]
        #ctx.bot.send_message(chat_id = upd.effective_chat.id, text = camel.__str__())
        camel.update(camel[["C", "A", "M", "E", "L"]].applymap('{:,.3f}'.format))
        sendTable(camel, upd, ctx)
        general = db.getGeneral(RIC)
        displayCAMEL(upd, ctx, df, general[0][1])
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
            lg.warning("Bad command")
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
        
        test = pd.DataFrame(columns=["x", "a", "b"])
        x = [0, 1, 2, 3]
        a = [1, 0, 1, 0]
        b = [3, 2, 1, 0]
        for i in range(len(x)):
            test = test.append({
                    "x" : x[i],
                    "a" : a[i],
                    "b" : b[i],
            }, ignore_index = True)
       
        plt.plot(test["x"], test[["a", "b"]])
        plt.savefig("test.png")
        
        ctx.bot.send_photo(chat_id = update.effective_chat.id, photo = open(path, "rb"))
        
        #context.bot.send_message(chat_id = update.effective_chat.id, text = infoData["about_info"]["company_name"])
        

        #lg.info("FIN")
        #lg.info(finData)

def displayCAMEL(upd, ctx, df, bankName):
    ax_size = (11.7,8.27)
    fig, ax = plt.subplots(figsize = ax_size)
    years = list(map(int, df["year"].tolist()))
    plt.plot(years, df["C"])
    plt.plot(years, df["A"])
    plt.plot(years, df["M"])
    plt.plot(years, df["E"])
    plt.plot(years, df["L"])
    plt.legend(["C", "A", "M", "E", "L"], loc = "best")
    plt.title("CAMEL dynamics for: %s" % bankName)
    plt.xticks(years)
    plt.grid()
    path = imgPath("camel1", upd, ctx)
    plt.savefig(path)
    plt.close()
    ctx.bot.send_photo(chat_id = upd.effective_chat.id, photo = open(path, "rb"))
    
    ax_size = (11.7,8.27)
    fig, ax = plt.subplots(figsize = ax_size)
    for y in years:
        single = df[df["year"] == y]
        ax = ["C", "A", "M", "E", "L"]
        plt.plot(ax, [single[x] for x in ax])
    
    plt.legend(years)
    plt.grid()
    plt.title("CAMEL patterns for: %s" % bankName)
    path = imgPath("camel2", upd, ctx)
    plt.savefig(path)
    plt.close()
    ctx.bot.send_photo(chat_id = upd.effective_chat.id, photo = open(path, "rb"))

def displayGraph(upd, ctx, years, values, title, stats, ylabel, cur):
    update = upd
    print(stats)
    curStats = stats[stats["year"].isin(years)]
    ax_size = (11.7,8.27)
    fig, ax = plt.subplots(figsize = ax_size)
    ax.xaxis.set_ticks(years)
    plt.plot(years, values)
    plt.ticklabel_format(style='plain', axis='y')
    plt.grid()
    plt.title("%s in millions %s" % (title, cur))
    path = imgPath(ylabel, upd, ctx)
    plt.savefig(path)
    plt.close()
    ctx.bot.send_photo(chat_id = update.effective_chat.id, photo = open(path, "rb"))
    lst = ["gdp", "budget expence"]
    print(curStats["budget expence"].max())
    if curStats["budget expence"].max() < 10:
        lst = ["gdp"]
    for name in lst:
        res = []
        ys = []
        for i, y in enumerate(years):
            if not curStats[curStats["year"] == y].empty:
                res.append(values[i] / curStats.loc[curStats["year"] == y, name])
                ys.append(y)

        plt.plot(ys, res)
        plt.grid()
        path = imgPath(ylabel + name, upd, ctx)
        plt.xticks(ys)
        plt.title("%s / %s" % (title, name))
        plt.savefig(path)
        plt.close()
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
            "interest" : "interest_income",
            "non-interest" : "non_interes_income",

        }
        mapping = {
            "net_income" : "Net Income",
            "cash_and_due_from_banks" : "Cash & Due from banks",
            "total_loans" : "Loans",
            "total_assets" : "Total Assets",
            "total_equity" : "Total Equity",
            "non_interest_income" : "Non-interest income",
            "interest_income" : "Interest income",
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
        general = db.getGeneral(RIC)
        myCur = db.getCurrency(data["cid"].iloc[0])[0][0]
        rate = db.getCurrencyPair("USD", myCur)[2]
        cInfo = db.getCountryInfo(general[0][2])
        sCols = ["year", "gdp", "budget expence", "popul"]
        stats = pd.DataFrame([], columns = sCols)
        for x in cInfo:
            stats = stats.append({
                "year" : x[4],
                "gdp" : x[1] * rate / (10 ** 6),
                "budget expence" : x[2] * rate / (10 ** 6),
                "popul" : x[3]
            }, ignore_index = True)

        displayGraph(upd, ctx, years, net_income, mapping[commands[command]], stats,  "data", myCur)


def addRIC(upd, ctx):
    args = upd.message.text.split()
    if len(args) != 2:
        lg.warning("...")
    else:
        RIC = args[1]
        try:
            infoData, finData, whole = prs.getData(RIC)
        except:
            text = "I cannot get information about %s from reuters. Please, check your RIC" % RIC
            ctx.bot.send_message(chat_id=upd.effective_chat.id, text = text)
            return
        extr = [
            ("balance_sheet_annual_tables", "Cash & Due from Banks", "cash_and_due_from_banks", []),
            ("income_annual_tables", "Interest Income, Bank", "interest_income", []),
            ("income_annual_tables", "Non-Interest Income, Bank", "non_interest_income", []),
            ("balance_sheet_annual_tables", "Other Earning Assets, Total", "other_earning_assets", []),
            ("balance_sheet_annual_tables", "Total Assets", "total_assets", []),
            ("balance_sheet_annual_tables", "Total Deposits", "total_deposits", []),
            ("balance_sheet_annual_tables", "Total Equity", "total_equity", []),
            ("balance_sheet_annual_tables", "Net Loans", "net_loans", []),
            ("income_annual_tables", "Net Income", "net_income", []),
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
            if not db.checkCountry(df["country"].iloc[0]):
                lg.info("???")
                gdp = getGDP(country)
                popul = getPopul(country)
                debt = getDebt(country)
                
                if len(debt) == 0:
                    for x in gdp:
                        debt[x] = 0.0
                
                if len(popul) == 0:
                    for x in gdp:
                        popul[x] = 0.0


                #print(gdp.keys())
                #print(popul.keys())
                #print(debt.keys())

                intY = list(set(gdp.keys()) & set(popul.keys()) & set(debt.keys()))

                cRows = []
                cCols = []
                
                cRows.append(currency)
                cCols.append("currency_name")
                
                cRows.append(df["country"].iloc[0])
                cCols.append("country_name")

                countryDf = pd.DataFrame([cRows], columns=cCols)
                db.addCountry(countryDf)
                print(intY)
                for y in intY:
                    iRows = []
                    iCols = []
                    
                    iRows.append(country)
                    iCols.append("country_name")

                    iRows.append(y)
                    iCols.append("year")

                    iRows.append(popul[y])
                    iCols.append("population")
                    
                    iRows.append(gdp[y])
                    iCols.append("gdp")
                    
                    print(y, gdp[y], debt[y])
                    iRows.append(gdp[y] * debt[y] / 100.0)
                    iCols.append("external_debt")
                    
                    infDf = pd.DataFrame([iRows], columns=iCols)
                    print(infDf)
                    db.addCountryInfo(infDf)
                lg.info("New country %s" % df["country"].iloc[0])

            res = db.addBank(RIC, df)
            addUpdateCur("USD", currency)
            addUpdateCur(currency, "USD")
            if not res:
                lg.info("Already exists")
            else:
                lg.info("Written")
                lg.info((df["year"], company))
        text = "%s is successfully added to our database!" % company
        ctx.bot.send_message(chat_id=upd.effective_chat.id, text = text)

def addUpdateCur(cur1, cur2):
    curRows = []
    curCols = []

    curRows.append(cur1)
    curCols.append("currency1_name")

    curRows.append(cur2)
    curCols.append("currency2_name")

    curRows.append(getRate(cur1, cur2))
    curCols.append("currency_price")

    curDf = pd.DataFrame([curRows], columns = curCols)
    res2 = db.addCurrencyPair(curDf)


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

camel_handler = CommandHandler('camel', getCAMELBase)
dispatcher.add_handler(camel_handler)

test_handler = CommandHandler('test', getFin)
dispatcher.add_handler(test_handler)

echo_handler = MessageHandler(Filters.text & (~Filters.command), echo)
dispatcher.add_handler(echo_handler)

updater.start_polling()

print(disp)
