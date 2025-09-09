from random import random,randint
import matplotlib.pyplot as plt
import numpy as np
import gspread
from google.oauth2 import service_account
import time
import mplfinance as mpf
import pandas as pd
from datetime import datetime, timedelta
import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from ai_commenter import AICommenter
from matplotlib.ticker import FuncFormatter
from dotenv import load_dotenv
import os

# Load env variables
load_dotenv()

# Load Google sheet
credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE")
google_url = os.getenv("GOOGLE_URL")

gc = gspread.service_account(filename=credentials_file)
sheet = gc.open_by_url(google_url)

# List all the worksheets in the Google Sheet
worksheet_list = sheet.worksheets()

worksheet = worksheet_list[0]
worksheet2 = worksheet_list[1]


custom_style = mpf.make_mpf_style(base_mpl_style='dark_background', 
                                  rc={'figure.facecolor': 'black',
                                      'axes.facecolor': 'black', 
                                      'axes.edgecolor': 'black', 
                                      'axes.labelcolor': 'white', 
                                      'xtick.color': 'white', 
                                      'ytick.color': 'white', 
                                      'grid.color': 'gray', 
                                      'grid.alpha': 0}, marketcolors=mpf.make_marketcolors(up='green', down='red', 
                                                                     edge='inherit', 
                                                                     wick='inherit', 
                                                                     volume='inherit'))

def dfs_from_l_bieres(l_bieres):
    """Construit un dict {nom_biere: df} depuis ta liste d'objets."""
    return {b.nom: b.df for b in l_bieres}

class biere:
    def __init__(self,prix_ini,nom,qte,prc,alpha,i,j,sheet):
        
        self.nom = nom
        self.prix = prix_ini
        self.alpha_a = 0.02
        self.h_prix = [self.prix]
        self.i = i
        self.j = j
        self.h_ventes = [0]
        self.h_prix = [self.prix]
        now = datetime.now()
        self.df = pd.DataFrame({
            'Open': self.prix,
            'High': self.prix,
            'Low': self.prix,
            'Close': self.prix,
            'Volume' : 100
        }, index=[now])
        self.open = self.prix
        self.high = self.prix
        self.low = self.prix
        self.close = self.prix
        self.qte = qte
        self.prc = prc
        self.sheet = sheet
        
    def liste_b(self,l):
        self.liste = l
        self.k = len(l)
        
    def achat(self,n):
        for _ in range(self.k):
            self.prix = self.prix*(1+random()*self.alpha_a)
            
    def vente(self,n):
        for _ in range(self.k):
            self.prix = self.prix*(1-random()*self.alpha_a/(self.k+0.2))
            
    def actualise(self):
        ventes = int(worksheet.cell(self.i, self.j).value)
        n = ventes - self.h_ventes[-1]
        #n = randint(0,2)
        if n > 0:
            self.achat(n)
            for b in self.liste:
                b.vente(n)
        self.h_prix.append(self.prix)
        self.h_ventes.append(ventes)
        
    def actualise_df(self):
        self.high = max(self.prix,self.high)
        self.low = min(self.prix,self.low)
        now = datetime.now()
        self.df.iloc[-1] = pd.DataFrame({
            'Open': self.open,
            'High': self.high,
            'Low': self.low,
            'Close': self.prix,
            'Volume' : 100
        }, index=[now])
    """
    def actualise_sheet(self,k):
        self.sheet.update_cell(4*(self.j-1) +1,k+2,self.open)
        self.sheet.update_cell(4*(self.j-1) +2,k+2,self.high)
        self.sheet.update_cell(4*(self.j-1) +3,k+2,self.low)
        self.sheet.update_cell(4*(self.j-1) +4,k+2,self.close)
    """
        
    def actualise_bougie(self):
        now = datetime.now()
        new_row = pd.DataFrame({
            'Open': self.prix,
            'High': self.prix,
            'Low': self.prix,
            'Close': self.prix,
            'Volume' : 100
        }, index=[now])
        self.open = self.prix
        self.close = self.prix
        self.high = self.prix
        self.low = self.prix
        self.df = pd.concat([self.df, new_row])
        
    def affiche(self):
        fig,ax = mpf.plot(self.df.tail(15),type='candle',style=custom_style)

def actualise_df(l_bieres):
    for b in l_bieres:
        b.actualise()
    for b in l_bieres:
        b.actualise_df()
    
def actualise_bougie(l_bieres):
    for b in l_bieres:
        b.actualise_bougie()
    for b in l_bieres:
        b.actualise()

def actualise_graph(l_canvas, l_fig_ax, l_bieres,l_label, root, ai, footer, k = 0):
    print('a')
    if k%4 == 0:
        actualise_bougie(l_bieres)
    else:
        actualise_df(l_bieres)
        """
    for b in l_bieres:
        b.actualise_sheet(k)
    """
    
    if k%2 == 0:
        ai.update_footer_async(root=root, footer_label=footer, dfs=dfs_from_l_bieres(l_bieres))        
    
    for i in range(len(l_fig_ax)):
        l_fig_ax[i][1][0].clear()
        plt.rc('xtick', labelsize=8)
        mpf.plot(l_bieres[i].df.tail(15),ax = l_fig_ax[i][1][0],type='candle',ylabel='',style=custom_style,returnfig=False)

        ax = l_fig_ax[i][1][0]
        ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.1f}"))


        l_canvas[i].draw()
        l_label[i].config(text = l_bieres[i].nom + " " + str(round(l_bieres[i].prix,2)) + "€")
    root.after(15000, actualise_graph, l_canvas, l_fig_ax, l_bieres,l_label, root, ai, footer, k+1)
    
if __name__ == "__main__":
    
    # Get beers infos
    sheet = worksheet_list[1]
    
    corona = biere(1.7,"Corona",33,4.5,0.03,1,1,sheet)
    despe = biere(2.5,"Desperados",33,5.9,0.03,11,1,sheet)
    chouffe = biere(2.9,"Chouffe",33,8.0,0.03,21,1,sheet)
    triple_k = biere(3,"Triple Karmelite",33,8.0,0.03,1,4,sheet)
    leffe = biere(1.8,"Leffe",25,6.6,0.03,11,4,sheet)
    goudale = biere(4,"Goudale",75,7.2,0.03,21,4,sheet)
    otcho = biere(3.2,"Otcho",33,8.0,0.03,1,7,sheet)
    vedett = biere(3,"Vedett",33,5.5,0.03,11,7,sheet)#
    brewdog = biere(2.8,"Brewdog Punk",33,5.6,0.03,21,7,sheet)
    seize = biere(1.7,"1664 blanche",25,5.5,0.03,1,10,sheet)
    chouffe_b = biere(3,"Chouffe blanche",33,6.5,0.03,11,10,sheet)
    kasteel = biere(3,"Kasteel rouge",33,8.0,0.03,21,10,sheet)
    chouffe_c = biere(3,"Chouffe Cherry",33,8.0,0.03,1,13,sheet)
    queue_de_charrue = biere(2.8,"Queue de charrue",33,5.5,0.03,11,13,sheet)
    kwak = biere(2.8,"Kwak",33,8.4,0.03,21,13,sheet)
    
    l_bieres = [corona,
    despe,
    chouffe,
    triple_k,
    leffe,
    goudale,
    otcho,
    vedett,
    brewdog,
    seize,
    chouffe_b,
    kasteel,
    chouffe_c,
    queue_de_charrue,
    kwak]

    # Init AI commenter
    ai = AICommenter()

    
    for i in range(len(l_bieres)):
        l_bieres[i].liste_b(l_bieres[:i]+l_bieres[i+1:])
    
    # Create Tkinter window
    root = tk.Tk()
    root.wm_title("Shhark")
    
    # Create mpf graphs
    l_fig_ax = [mpf.plot(l_bieres[i].df.tail(22),type='candle',figsize=(1.45, 1.2),ylabel='',style=custom_style,returnfig=True) for i in range(15)]

    # Mofify police size in graphs (to fit in fullscreen, with hand)
    for fig, axes in l_fig_ax:
        for ax in axes:
            ax.tick_params(axis='x', labelsize=3)
            ax.tick_params(axis='y', labelsize=5)
    
    # -------- Pack Graphs
    l_frame =  [tk.Frame(root) for i in range(15)]
    
    for i in range(len(l_frame)) :
        l_frame[i].grid(row = i%3,column = i//3)
    l_canvas = [FigureCanvasTkAgg(l_fig_ax[i][0], master=l_frame[i]) for i in range(15)]
    l_label = [tk.Label(l_frame[i], text=l_bieres[i].nom, font=('Arial', 18),bg="black", fg="white") for i in range(15)]
    
    for i in range(len(l_canvas)):
        l_canvas[i].get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        l_label[i].pack(side=tk.BOTTOM, fill=tk.X)
    
    # -------- Pack footer (AiCommenter)
    footer = tk.Label(root, text="Données en cours...", font=("Arial", 14),
                    bg="black", fg="white",wraplength=800, justify="center")
    footer.grid(row=3, column=0, columnspan=5, sticky="ew", pady=30)

    # Update loop
    root.after(150, actualise_graph, l_canvas, l_fig_ax, l_bieres,l_label, root, ai, footer)
    
    # Tkinter window configuration
    root.configure(bg='black')
    root.attributes('-fullscreen', True)
    
    root.mainloop()