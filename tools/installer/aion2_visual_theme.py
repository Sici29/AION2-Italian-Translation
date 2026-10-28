"""Shared presentation layer. Official NC artwork; no game or network operations."""
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk

def resource(name):
    return Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'visual_assets'/name

def prepare_window(root,width,height):
    available=max(620,root.winfo_screenheight()-90)
    root.geometry(f'{width}x{min(height,available)}')
    root.minsize(min(width,710),min(680,available))
    root.configure(background='#101b27')
    root._italian_icon=tk.PhotoImage(file=str(resource('aion2-italiano.png')))
    root.iconphoto(True,root._italian_icon)
    style=ttk.Style(root);style.theme_use('clam')
    style.configure('.',font=('Segoe UI',10),background='#f1f4f7',foreground='#172b40')
    style.configure('TButton',padding=(10,7))
    style.map('TButton',background=[('active','#dbe7ee'),('disabled','#e5e9ed')])
    style.configure('TEntry',fieldbackground='white',padding=4)

def add_header(root,title,subtitle,art):
    compact=root.winfo_screenheight()<900
    header=tk.Frame(root,bg='#101b27');header.pack(fill='x')
    image=tk.PhotoImage(file=str(resource(art)))
    if compact:image=image.subsample(2,2)
    image_label=tk.Label(header,image=image,bg='#101b27',borderwidth=0)
    image_label.image=image;image_label.pack(side='left')
    content=tk.Frame(header,bg='#101b27');content.pack(side='left',fill='both',expand=True,padx=20,pady=12)
    tk.Label(content,text='AION 2',font=('Segoe UI',23,'bold'),fg='#e5f7ff',bg='#101b27').pack(anchor='w')
    row=tk.Frame(content,bg='#101b27');row.pack(anchor='w',pady=5)
    flag=tk.Canvas(row,width=30,height=18,bg='#101b27',highlightthickness=0)
    for i,color in enumerate(['#009246','#ffffff','#ce2b37']):flag.create_rectangle(i*10,0,(i+1)*10,18,fill=color,outline='')
    flag.pack(side='left',padx=(0,8))
    tk.Label(row,text=title,font=('Segoe UI',11,'bold'),fg='#92d9ed',bg='#101b27').pack(side='left')
    tk.Label(content,text=subtitle,font=('Segoe UI',10),fg='#c1cddd',bg='#101b27').pack(anchor='w')
    tk.Label(root,text='Traduzione amatoriale · Artwork e logo © NC Corporation',font=('Segoe UI',8),fg='#a8b9c8',bg='#101b27').pack(fill='x',ipady=3)
    return image_label
