"""Panel simple de Windows. Abrirlo no realiza solicitudes de red."""
import os
import json
import re
from datetime import datetime
from pathlib import Path
import queue
import sys
import tempfile
import threading
import tkinter as tk
import warnings
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageOps, ImageTk
from i18n import translate
from core import import_package, update_package, normalize_token, valid_token, export_local_desktop, export_zip, load_config, request, resolve_channel, save_config, validate, package_name

BASE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
DATA = Path(os.environ.get('APPDATA', Path.home())) / 'SelfBot Simple' / 'config.json'
PREFS = DATA.with_name('appearance.json')


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('SELF BOT DISCORD')
        screen_width, screen_height = self.winfo_screenwidth(), self.winfo_screenheight()
        width, height = min(820, screen_width - 80), min(860, screen_height - 100)
        self.geometry(f'{width}x{height}')
        self.minsize(min(680, width), min(600, height))
        self.resizable(False, False)
        self.configure(bg='#f2f5fa')
        self.busy = False
        self.language = tk.StringVar(value='Español')
        self.theme_display = tk.StringVar(value='Claro')
        self.status_source = 'Listo. Configura los datos para empezar.'
        self.account_source = 'Sin comprobar'
        self.confirmed_account = None
        self.events = queue.Queue()
        self.image = tk.StringVar()
        self.image_valid = False
        self.preview_photo = None
        self.token = tk.StringVar()
        self.minutes = tk.StringVar(value='30')
        self.status = tk.StringVar(value='Listo. Configura los datos para empezar.')
        self.counter = tk.StringVar(value='0 / 2000 caracteres')
        self.account_status = tk.StringVar(value='Sin comprobar')
        self.account_level = 'info'
        self.theme = tk.StringVar(value='Claro')
        self.channel_id = tk.StringVar()
        self.channel_rows = []
        self.error_entries = []
        self.loaded_source = None
        self.loaded_name = tk.StringVar()
        self.readiness = tk.StringVar()
        self.pending = tk.StringVar()
        style = ttk.Style(self)
        self.style = style
        style.theme_use('clam')
        style.configure('TFrame', background='#f2f5fa')
        style.configure('TLabel', background='#f2f5fa', foreground='#25324a', font=('Segoe UI', 10))
        style.configure('Hint.TLabel', foreground='#65718a', font=('Segoe UI', 9))
        style.configure('Title.TLabel', font=('Segoe UI', 21, 'bold'), foreground='#13203a')
        style.configure('Section.TLabel', font=('Segoe UI', 11, 'bold'))
        style.configure('TButton', padding=(12, 9), font=('Segoe UI', 10))
        style.configure('Primary.TButton', background='#2563eb', foreground='white')
        style.map('Primary.TButton', background=[('active', '#1d4ed8'), ('disabled', '#9aaed9')])
        style.configure('TEntry', padding=7)
        self.footer = ttk.Frame(self, padding=(24, 12))
        self.footer.pack(side='bottom', fill='x')
        canvas = tk.Canvas(self, bg='#f2f5fa', highlightthickness=0)
        self.canvas = canvas
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=canvas.yview)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        outer = ttk.Frame(canvas, padding=(24, 22), style='Outer.TFrame')
        shell = outer
        self.card_borders = []
        window_id = canvas.create_window((0, 0), window=outer, anchor='nw')
        outer.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        def fit(event):
            width = min(event.width, 820)
            canvas.itemconfigure(window_id, width=width)
            canvas.coords(window_id, max(0, (event.width-width)//2), 0)
        canvas.bind('<Configure>', fit)
        self.bind('<MouseWheel>', lambda event: canvas.yview_scroll(-int(event.delta / 120), 'units') if canvas.bbox('all')[3] > canvas.winfo_height() else None)
        header = ttk.Frame(outer, style='Outer.TFrame')
        header.pack(fill='x')
        ttk.Label(header, text='SELF BOT DISCORD', style='Title.TLabel').pack(side='left')
        theme_row = ttk.Frame(outer, style='Outer.TFrame')
        theme_row.pack(fill='x', pady=(8, 0))
        ttk.Label(theme_row, text='TEMA', style='HeaderHint.TLabel').pack(side='left', padx=6)
        self.theme_selector = ttk.Combobox(theme_row, textvariable=self.theme_display, values=['Claro', 'Oscuro'], state='readonly', width=9)
        self.theme_selector.pack(side='left')
        self.theme_selector.bind('<<ComboboxSelected>>', self.change_theme)
        ttk.Label(theme_row, text='IDIOMA', style='HeaderHint.TLabel').pack(side='left', padx=(20, 6))
        self.language_selector = ttk.Combobox(theme_row, textvariable=self.language, values=['Español', 'English'], state='readonly', width=10)
        self.language_selector.pack(side='left')
        self.language_selector.bind('<<ComboboxSelected>>', self.change_language)
        ttk.Label(outer, text='Tu cuenta, tus canales y tus mensajes. Todo en un solo lugar.', style='HeaderHint.TLabel').pack(anchor='w', pady=(6, 12))

        outer = self.section(shell, '01', 'Tu cuenta')
        ttk.Label(outer, text='Token de Cuenta:', style='Hint.TLabel').pack(anchor='w')
        row = ttk.Frame(outer)
        row.pack(fill='x', pady=(5, 5))
        self.secret = ttk.Entry(row, textvariable=self.token, show='•')
        self.secret.pack(side='left', fill='x', expand=True)
        self.show_secret = tk.BooleanVar(value=False)
        self.reveal = ttk.Checkbutton(row, text='Ver', variable=self.show_secret, command=lambda: self.secret.configure(show='' if self.show_secret.get() else '•'))
        self.reveal.pack(side='left', padx=(8, 0))
        row2 = ttk.Frame(outer)
        row2.pack(fill='x')
        self.check_button = ttk.Button(row2, text='Comprobar cuenta', style='Primary.TButton', command=self.check_account)
        self.check_button.pack(side='left')
        ttk.Label(row2, text='Solo consulta el acceso.', style='Hint.TLabel').pack(side='left', padx=10)
        self.account_label = ttk.Label(outer, textvariable=self.account_status, style='AccountInfo.TLabel', padding=(10, 8), wraplength=630)
        self.account_label.pack(fill='x', pady=(10, 0))

        outer = self.section(shell, '02', 'Canales de destino')
        ttk.Label(outer, text='Pega un ID y pulsa Agregar para identificar el canal y su servidor.', style='Hint.TLabel', wraplength=650).pack(anchor='w', pady=(3, 5))
        channel_row = ttk.Frame(outer)
        channel_row.pack(fill='x', pady=(0, 6))
        self.channel_entry = ttk.Entry(channel_row, textvariable=self.channel_id)
        self.channel_entry.pack(side='left', fill='x', expand=True, padx=(0, 8))
        self.channel_entry.bind('<Return>', lambda event: self.add_channel())
        self.add_channel_button = ttk.Button(channel_row, text='Agregar', command=self.add_channel)
        self.add_channel_button.pack(side='left')
        table_row = ttk.Frame(outer)
        table_row.pack(fill='x')
        self.channel_table = ttk.Treeview(table_row, columns=('name', 'group', 'id'), show='headings', height=3, selectmode='browse')
        for column, label, width in [('name', 'Canal', 170), ('group', 'Servidor / grupo', 220), ('id', 'ID', 180)]:
            self.channel_table.heading(column, text=label)
            self.channel_table.column(column, width=width, minwidth=80, stretch=True)
        table_scroll = ttk.Scrollbar(table_row, command=self.channel_table.yview)
        self.channel_table.configure(yscrollcommand=table_scroll.set)
        table_scroll.pack(side='right', fill='y')
        self.channel_table.pack(side='left', fill='x', expand=True)
        channel_actions = ttk.Frame(outer)
        channel_actions.pack(fill='x', pady=(5, 0))
        self.delete_channel_button = ttk.Button(channel_actions, text='Quitar seleccionado', command=self.remove_channel)
        self.delete_channel_button.pack(side='left')

        outer = self.section(shell, '03', 'Tu mensaje')
        self.message = self.textbox(outer, height=4)
        self.message.bind('<<Modified>>', self.update_count)
        ttk.Label(outer, textvariable=self.counter, style='Hint.TLabel').pack(anchor='e', pady=(3, 5))
        imgrow = ttk.Frame(outer)
        imgrow.pack(fill='x')
        self.choose_button = ttk.Button(imgrow, text='Añadir imagen', command=self.pick_image)
        self.choose_button.pack(side='left')
        self.remove_button = ttk.Button(imgrow, text='Quitar', command=lambda: self.image.set(''))
        self.remove_button.pack(side='left', padx=(6, 10))
        self.image_label = ttk.Label(imgrow, text='Sin imagen · opcional', style='Hint.TLabel', wraplength=390)
        self.image_label.pack(side='left', fill='x', expand=True)
        self.preview_frame = ttk.Frame(outer)
        ttk.Label(self.preview_frame, text='Vista previa del mensaje', style='Section.TLabel').pack(anchor='w', pady=(0, 5))
        self.message_preview = ttk.Label(self.preview_frame, style='Preview.TLabel', wraplength=580, padding=10, justify='left')
        self.message_preview.pack(fill='x', pady=(0, 6))
        self.preview_label = ttk.Label(self.preview_frame, style='Preview.TLabel', anchor='center', padding=10)
        self.preview_label.pack(fill='x')
        self.preview_caption = ttk.Label(self.preview_frame, style='Hint.TLabel', wraplength=630)
        self.preview_caption.pack(anchor='w', pady=(4, 0))
        self.image.trace_add('write', self.update_image_preview)

        outer = self.section(shell, '04', 'Cuándo enviar')
        row = ttk.Frame(outer)
        row.pack(fill='x', pady=(5, 4))
        ttk.Label(row, text='Espera entre rondas (±15 %)').pack(side='left')
        self.interval = ttk.Entry(row, textvariable=self.minutes, width=8)
        self.interval.pack(side='left', padx=8)
        ttk.Label(row, text='minutos').pack(side='left')
        ttk.Label(outer, text='Al iniciar el bot en Discloud, la primera ronda comienza de inmediato.', style='Hint.TLabel', wraplength=650).pack(anchor='w')

        outer = self.footer
        import_actions = ttk.Frame(outer)
        import_actions.pack(fill='x', pady=(0, 5))
        self.load_button = ttk.Button(import_actions, text='Cargar BAT o ZIP', command=self.load_package)
        self.load_button.pack(side='left')
        self.update_button = ttk.Button(import_actions, text='Actualizar archivo cargado', command=self.update_loaded, state='disabled')
        self.update_button.pack(side='right')
        ttk.Label(outer, textvariable=self.loaded_name, style='Hint.TLabel', wraplength=650).pack(anchor='w', pady=(0, 5))
        export_actions = ttk.Frame(outer)
        export_actions.pack(fill='x', pady=(0, 5))
        self.zip_button = ttk.Button(export_actions, text='Generar ZIP para Discloud', style='Primary.TButton', command=self.export)
        self.zip_button.pack(side='left')
        self.local_button = ttk.Button(export_actions, text='Crear BAT en Escritorio', command=self.export_local)
        self.local_button.pack(side='right')
        ttk.Label(outer, text='Los paquetes incluyen la credencial para que el bot funcione. No los compartas.', style='Hint.TLabel', wraplength=650).pack(anchor='w', pady=(3, 10))
        ttk.Separator(outer).pack(fill='x')
        self.readiness_label = ttk.Label(outer, textvariable=self.readiness, wraplength=700)
        self.readiness_label.pack(anchor='w', pady=(8, 0))
        ttk.Label(outer, textvariable=self.pending, style='Hint.TLabel').pack(anchor='w')
        self.status_label = ttk.Label(outer, textvariable=self.status, style='StatusInfo.TLabel', wraplength=740)
        self.status_label.pack(anchor='w', pady=(8, 0))
        self.controls = [self.secret, self.reveal, self.channel_entry,
                         self.add_channel_button, self.delete_channel_button, self.message,
                         self.interval, self.check_button, self.choose_button, self.remove_button,
                         self.zip_button, self.local_button, self.load_button, self.update_button]
        self.restore()
        self.token.trace_add('write', self.invalidate_channel_names)
        self.static_texts = []
        def collect(widget):
            if isinstance(widget, (ttk.Label, ttk.Button, ttk.Checkbutton)) and widget not in (self.image_label, self.message_preview, self.preview_caption):
                text = widget.cget('text')
                if text:
                    self.static_texts.append((widget, str(text)))
            for child in widget.winfo_children():
                collect(child)
        collect(self)
        try:
            preferences = json.loads(PREFS.read_text(encoding='utf-8'))
            preference = preferences.get('theme', 'Claro')
            self.theme.set(preference if preference in ('Claro', 'Oscuro') else 'Claro')
            language = preferences.get('language', 'Español')
            self.language.set(language if language in ('Español', 'English') else 'Español')
        except (OSError, ValueError, AttributeError):
            pass
        self.apply_theme()
        self.apply_language()
        self.minutes.trace_add('write', lambda *_: self.refresh_form())
        self.image.trace_add('write', lambda *_: self.refresh_form())
        self.update_image_preview()
        self.refresh_form()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.poll_timer = self.after(100, self.poll)

    def section(self, parent, number, title):
        border = tk.Frame(parent, bg='#dce3ef', padx=1, pady=1)
        border.pack(fill='x', pady=(0, 12))
        self.card_borders.append(border)
        card = ttk.Frame(border, padding=(18, 14))
        card.pack(fill='x')
        title_row = ttk.Frame(card)
        title_row.pack(fill='x', pady=(0, 10))
        ttk.Label(title_row, text=number, style='Number.TLabel', padding=(8, 4)).pack(side='left', padx=(0, 10))
        ttk.Label(title_row, text=title, style='Section.TLabel').pack(side='left')
        return card

    def set_status(self, text, level='info'):
        text = self.safe_text(text)
        self.status_source = text
        if level == 'error':
            self.error_entries.append(datetime.now().strftime('%H:%M:%S') + ' · ' + text)
            self.error_entries = self.error_entries[-100:]
        self.status.set(self.tr(text))
        self.status_label.configure(style={'success': 'StatusSuccess.TLabel', 'error': 'StatusError.TLabel'}.get(level, 'StatusInfo.TLabel'))

    def set_account_status(self, text, level='info'):
        self.account_level = level
        self.account_source = self.safe_text(text)
        self.account_status.set(self.tr(self.account_source))
        self.account_label.configure(style={'success': 'AccountSuccess.TLabel', 'error': 'AccountError.TLabel'}.get(level, 'AccountInfo.TLabel'))

    def apply_theme(self):
        dark = self.theme.get() == 'Oscuro'
        bg, field, fg, muted, border = (
            ('#151b26', '#202a3a', '#edf2fa', '#acbad0', '#3d4b60') if dark else
            ('#f2f5fa', '#ffffff', '#25324a', '#65718a', '#c3ccda'))
        hover = '#31425c' if dark else '#e0e7f1'
        disabled = '#8b99af' if dark else '#748198'
        card = '#1c2535' if dark else '#ffffff'
        success = '#86efac' if dark else '#166534'
        error = '#fda4af' if dark else '#b91c1c'
        style = self.style
        self.configure(bg=bg)
        self.canvas.configure(bg=bg)
        for name in ('TFrame', 'TLabel', 'TCheckbutton'):
            style.configure(name, background=card, foreground=fg)
        style.configure('Outer.TFrame', background=bg)
        for widget in self.card_borders:
            widget.configure(bg=border)
        style.configure('HeaderHint.TLabel', background=bg, foreground=muted, font=('Segoe UI', 9))
        style.configure('Number.TLabel', background='#273a5d' if dark else '#eaf0ff', foreground='#a5c4ff' if dark else '#2563eb', font=('Segoe UI', 10, 'bold'))
        for name, color in [('StatusInfo.TLabel', muted), ('StatusSuccess.TLabel', success), ('StatusError.TLabel', error)]:
            style.configure(name, background=card, foreground=color, font=('Segoe UI', 10, 'bold'))
        for name, color, fill in [('AccountInfo.TLabel', muted, field),
                                  ('AccountSuccess.TLabel', success, '#173c2e' if dark else '#ecfdf3'),
                                  ('AccountError.TLabel', error, '#442432' if dark else '#fff1f2')]:
            style.configure(name, background=fill, foreground=color, font=('Segoe UI', 10, 'bold'))
        style.configure('Hint.TLabel', foreground=muted)
        style.configure('Preview.TLabel', background=field, foreground=fg, borderwidth=1, relief='solid', bordercolor=border)
        style.configure('PreviewError.TLabel', background=card, foreground=error, font=('Segoe UI', 9))
        style.configure('Title.TLabel', foreground=fg, background=bg)
        style.configure('TButton', background=field, foreground=fg, bordercolor=border)
        style.map('TButton', background=[('disabled', bg), ('active', hover)], foreground=[('disabled', disabled)])
        style.configure('Primary.TButton', background='#2563eb', foreground='#ffffff')
        style.map('Primary.TButton', background=[('disabled', '#405577' if dark else '#9aaed9'), ('active', '#1d4ed8')], foreground=[('disabled', '#d5deed'), ('!disabled', '#ffffff')])
        for name in ('TEntry', 'TCombobox'):
            style.configure(name, fieldbackground=field, background=field, foreground=fg,
                            insertcolor=fg, bordercolor=border, arrowcolor=fg,
                            selectbackground='#2563eb', selectforeground='#ffffff')
            style.map(name, fieldbackground=[('disabled', bg), ('readonly', field)],
                      foreground=[('disabled', disabled), ('readonly', fg)],
                      background=[('active', hover), ('readonly', field)])
        style.map('TCheckbutton', background=[('active', card)], foreground=[('disabled', disabled)])
        style.configure('TSeparator', background=border)
        style.configure('Vertical.TScrollbar', background=border, troughcolor=bg, arrowcolor=fg, bordercolor=bg)
        style.map('Vertical.TScrollbar', background=[('active', hover)])
        style.configure('Treeview', background=field, fieldbackground=field, foreground=fg, rowheight=26, bordercolor=border, font=('Segoe UI', 10))
        style.map('Treeview', background=[('selected', '#2563eb')], foreground=[('selected', '#ffffff')])
        style.configure('Treeview.Heading', background=hover, foreground=fg, font=('Segoe UI', 9, 'bold'))
        style.map('Treeview.Heading', background=[('active', hover)])
        self.option_add('*TCombobox*Listbox.background', field)
        self.option_add('*TCombobox*Listbox.foreground', fg)
        self.option_add('*TCombobox*Listbox.selectBackground', '#2563eb')
        self.option_add('*TCombobox*Listbox.selectForeground', '#ffffff')
        # Existing dropdowns retain their Tk options after the first opening.
        for combo in (self.theme_selector, self.language_selector):
            popup = self.tk.call('ttk::combobox::PopdownWindow', str(combo))
            self.tk.call(str(popup) + '.f.l', 'configure', '-background', field,
                         '-foreground', fg, '-selectbackground', '#2563eb', '-selectforeground', '#ffffff')
        for box in (self.message,):
            box.configure(bg=field, fg=fg, insertbackground=fg, selectbackground='#2563eb',
                          selectforeground='#ffffff', highlightbackground=border,
                          highlightcolor='#2563eb', highlightthickness=1)

    def tr(self, text):
        return translate(text, self.language.get())

    def apply_language(self):
        for widget, source in self.static_texts:
            widget.configure(text=self.tr(source))
        self.theme_selector.configure(values=[self.tr('Claro'), self.tr('Oscuro')])
        self.theme_display.set(self.tr(self.theme.get()))
        for column, source in [('name', 'Canal'), ('group', 'Servidor / grupo'), ('id', 'ID')]:
            self.channel_table.heading(column, text=self.tr(source))
        self.status.set(self.tr(self.status_source))
        self.account_status.set(self.tr(self.account_source))
        self.counter.set(self.tr(f'{len(self.message.get("1.0", "end-1c"))} / 2000 caracteres'))
        self.update_image_preview()
        self.refresh_form()
        # A log window uses the language selected when it is opened.
        for dialog in list(self.winfo_children()):
            if isinstance(dialog, tk.Toplevel) and getattr(dialog, 'error_log', False):
                dialog.destroy()

    def change_language(self, event=None):
        self.apply_language()
        self.save_preferences()

    def change_theme(self, event=None):
        self.theme.set('Oscuro' if self.theme_display.get() in ('Oscuro', 'Dark') else 'Claro')
        self.apply_theme()
        self.save_preferences()

    def save_preferences(self):
        temporary = None
        try:
            PREFS.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=PREFS.parent, delete=False) as f:
                temporary = f.name
                json.dump({'theme': self.theme.get(), 'language': self.language.get()}, f)
            os.replace(temporary, PREFS)
        except OSError:
            self.set_status('No se pudo guardar la preferencia en este equipo.', 'error')
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def heading(self, parent, text):
        ttk.Label(parent, text=text, style='Section.TLabel').pack(anchor='w', pady=(10, 5))

    def textbox(self, parent, height):
        frame = ttk.Frame(parent)
        frame.pack(fill='x')
        box = tk.Text(frame, height=height, wrap='word', font=('Segoe UI', 10), bg='white', fg='#25324a', relief='solid', borderwidth=1, padx=9, pady=7, undo=True)
        scroll = ttk.Scrollbar(frame, command=box.yview)
        box.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        box.pack(side='left', fill='x', expand=True)
        return box

    def update_count(self, event=None):
        if self.message.edit_modified():
            self.counter.set(self.tr(f'{len(self.message.get("1.0", "end-1c"))} / 2000 caracteres'))
            self.message.edit_modified(False)
            self.refresh_form()

    def snapshot(self):
        return dict(token=normalize_token(self.token.get()), account_type='personal',
                    channels=[row['id'] for row in self.channel_rows], channel_metadata=[dict(row) for row in self.channel_rows], message=self.message.get('1.0', 'end-1c'),
                    image=self.image.get(), minutes=self.minutes.get(),
                    read_before=True, typing_before=True, variable_pauses=True, delete_previous=True)

    def restore(self):
        if not DATA.exists():
            self.initial = self.snapshot()
            return
        try:
            c = load_config(DATA)
            self.token.set(c.get('token', ''))
            metadata = {str(row['id']): row for row in c.get('channel_metadata', []) if isinstance(row, dict) and 'id' in row}
            for channel in dict.fromkeys(c.get('channels', [])):
                self.channel_rows.append(dict(metadata.get(channel, {'id': channel, 'name': 'Sin comprobar', 'group': '—', 'guild_id': ''})))
            self.render_channels()
            self.message.insert('1.0', c.get('message', ''))
            self.image.set(c.get('image', ''))
            self.minutes.set(str(c.get('minutes', 30)))
            self.set_status('Configuración recuperada. La cuenta aún no se ha comprobado.')
        except Exception:
            self.set_status('No se pudo recuperar la configuración. Revisa los datos y vuelve a guardarlos.', 'error')
        self.initial = self.snapshot()

    def render_channels(self):
        selected = self.channel_table.selection()
        self.channel_table.delete(*self.channel_table.get_children())
        for row in self.channel_rows:
            self.channel_table.insert('', 'end', iid=row['id'], values=(row.get('name', 'Sin comprobar'), row.get('group', '—'), row['id']))
        if selected and self.channel_table.exists(selected[0]):
            self.channel_table.selection_set(selected[0])

    def refresh_form(self):
        if not hasattr(self, 'message_preview'):
            return
        text = self.message.get('1.0', 'end-1c')
        self.message_preview.configure(text=text or self.tr('Solo imagen' if self.image.get() else 'Tu mensaje aparecerá aquí.'))
        self.preview_frame.pack(fill='x', pady=(10, 0))
        c = self.snapshot()
        problem = None
        if not c['token']:
            problem = 'Falta el Token de Cuenta. Agrégalo en Tu cuenta.'
        elif not c['channels']:
            problem = 'Falta un canal. Agrega un ID en Canales de destino.'
        elif c['image'] and not self.image_valid:
            problem = 'Imagen inválida. Selecciona otra imagen o quítala.'
        else:
            try:
                validate(c)
            except (ValueError, OSError) as exc:
                problem = str(exc)
        self.readiness.set(('✕ ' + self.tr(problem)) if problem else '✓ ' + self.tr('Configuración lista') + (self.tr(' · cuenta sin comprobar') if self.account_level != 'success' else ''))
        self.readiness_label.configure(style='StatusError.TLabel' if problem else 'StatusSuccess.TLabel')
        dirty = hasattr(self, 'initial') and c != self.initial
        self.pending.set(self.tr('● Cambios sin guardar' if dirty else 'Sin cambios pendientes'))
        if hasattr(self, 'update_button'):
            self.update_button.configure(state='normal' if self.loaded_source and not self.busy else 'disabled')
            self.loaded_name.set(self.tr('Archivo cargado: {name}'.format(name=Path(self.loaded_source['path']).name)) if self.loaded_source else self.tr('Ningún archivo cargado'))

    def safe_text(self, value):
        text = str(value)
        for token in (self.token.get().strip(), normalize_token(self.token.get())):
            if token:
                text = text.replace(token, '[credencial oculta]')
        text = re.sub(r'(?i)(authorization|token)\s*[:=]\s*\S+', r'\1: [oculto]', text)
        return text

    def friendly_error(self, exc):
        status = getattr(exc, 'status', None)
        explanations = {
            401: 'Discord rechazó el token. Comprueba la credencial y vuelve a verificar la cuenta.',
            403: 'No tienes permiso para acceder a ese canal. Revisa los permisos y el ID.',
            404: 'No se encontró el canal. Revisa el ID y que la cuenta tenga acceso.',
            429: 'Discord pide esperar. Inténtalo de nuevo más tarde.'}
        if status in explanations:
            return explanations[status]
        if isinstance(exc, OSError):
            return 'No se pudo leer o guardar el archivo. Revisa que exista y que tengas permiso para acceder.'
        if isinstance(exc, RuntimeError):
            return 'No se pudo completar la operación. Revisa la conexión y vuelve a intentarlo; si estabas guardando, comprueba los permisos del equipo.'
        if isinstance(exc, ValueError):
            return self.safe_text(exc)
        return 'No se pudo completar la operación. Revisa los datos y vuelve a intentarlo.'

    def show_errors(self):
        dialog = tk.Toplevel(self)
        dialog.error_log = True
        dialog.title(self.tr('Registro de errores'))
        dialog.geometry('650x330')
        dialog.transient(self)
        ttk.Label(dialog, text=self.tr('Errores de esta sesión · se conservan los últimos 100'), padding=12).pack(anchor='w')
        box = self.textbox(dialog, 10)
        box.configure(bg=self.message.cget('bg'), fg=self.message.cget('fg'))
        box.insert('1.0', '\n\n'.join(entry.split(' · ', 1)[0] + ' · ' + self.tr(self.safe_text(entry.split(' · ', 1)[1])) for entry in self.error_entries) or self.tr('No hay errores en esta sesión.'))
        box.configure(state='disabled')
        ttk.Button(dialog, text=self.tr('Cerrar'), command=dialog.destroy).pack(pady=8)

    def invalidate_channel_names(self, *_):
        self.confirmed_account = None
        self.set_account_status('Sin comprobar · el token cambió')
        self.set_status('Token cambiado. Vuelve a comprobar la cuenta.')
        for row in self.channel_rows:
            row.update(name='Sin comprobar', group='—', guild_id='')
        self.render_channels()
        self.refresh_form()

    def add_channel(self):
        if self.busy:
            return
        channel = self.channel_id.get().strip()
        if any(row['id'] == channel for row in self.channel_rows):
            self.error(ValueError('Ese canal ya está en la lista.'))
            return
        token, kind = self.token.get(), 'personal'
        def added(row):
            self.channel_rows.append(row)
            self.render_channels()
            self.channel_table.selection_set(row['id'])
            self.channel_table.see(row['id'])
            self.channel_id.set('')
            self.refresh_form()
            return f'Agregado: {row["name"]} · {row["group"]}. Puedes guardar los cambios al cerrar.'
        self.worker(lambda: resolve_channel(token, kind, channel), added)

    def remove_channel(self):
        if self.busy:
            return
        selected = self.channel_table.selection()
        if not selected:
            self.set_status('Selecciona un canal de la lista para quitarlo.')
            return
        self.channel_rows = [row for row in self.channel_rows if row['id'] != selected[0]]
        self.render_channels()
        self.refresh_form()
        self.set_status('Canal quitado de esta lista. Puedes guardar los cambios al cerrar.', 'success')

    def error(self, exc):
        text = self.friendly_error(exc)
        self.set_status('Error: ' + text, 'error')
        messagebox.showerror(self.tr('Revisa los datos'), self.tr(text), parent=self)

    def save(self):
        try:
            c = self.snapshot()
            save_config(DATA, c)
            self.initial = c
            self.refresh_form()
            self.set_status('✓ Configuración guardada en este equipo.', 'success')
            return True
        except Exception as exc:
            self.error(exc)
            return False

    def pick_image(self):
        path = filedialog.askopenfilename(parent=self, title=self.tr('Seleccionar una imagen'), filetypes=[(self.tr('Imágenes'), '*.png *.jpg *.jpeg *.gif *.webp')])
        if path:
            self.image.set(path)

    def update_image_preview(self, *_):
        path = self.image.get()
        self.image_valid = False
        self.preview_photo = None
        self.preview_label.configure(image='', text='')
        self.preview_frame.pack_forget()
        if not path:
            self.image_label.configure(text=self.tr('Sin imagen · opcional'))
            self.preview_label.pack_forget()
            self.preview_caption.configure(text='')
            self.refresh_form()
            return
        self.image_label.configure(text=Path(path).name)
        try:
            size = Path(path).stat().st_size
            if size > 10 * 1024 * 1024:
                raise ValueError('La imagen supera los 10 MB permitidos.')
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(path) as original:
                    width, height = original.size
                    preview = ImageOps.exif_transpose(original)
                    preview.thumbnail((560, 200), Image.Resampling.LANCZOS)
                    self.preview_photo = ImageTk.PhotoImage(preview.convert('RGBA'), master=self)
            self.preview_label.configure(image=self.preview_photo, style='Preview.TLabel')
            self.preview_label.pack(fill='x', before=self.preview_caption)
            self.preview_caption.configure(text=f'{width} × {height} px · {size / 1024:.0f} KB', style='Hint.TLabel')
            self.image_valid = True
        except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning, tk.TclError) as exc:
            self.preview_label.pack_forget()
            text = str(exc) if isinstance(exc, ValueError) else 'No se pudo abrir esta imagen. Selecciona otra.'
            self.preview_caption.configure(text='✕ ' + self.tr(text), style='PreviewError.TLabel')
        self.preview_frame.pack(fill='x', pady=(10, 0))
        self.refresh_form()

    def worker(self, task, success, context=None):
        if self.busy:
            return
        self.busy = True
        self.set_status('Procesando…')
        if context == 'account':
            self.set_account_status('Comprobando token…')
        for widget in self.controls:
            widget.configure(state='disabled')
        def job():
            try:
                self.events.put((True, task(), success, context))
            except Exception as exc:
                self.events.put((False, exc, None, context))
        threading.Thread(target=job, daemon=True).start()

    def poll(self):
        try:
            ok, result, success, context = self.events.get_nowait()
            self.busy = False
            for widget in self.controls:
                widget.configure(state='normal')
            try:
                text = success(result) if ok else self.friendly_error(result)
            except Exception as exc:
                ok, text = False, self.friendly_error(exc)
            self.set_status(text if ok else 'Error: ' + text, 'success' if ok else 'error')
            if context == 'account':
                self.set_account_status(text if ok else '✕ ' + text, 'success' if ok else 'error')
            self.refresh_form()
            if not ok and context != 'account':
                messagebox.showerror(self.tr('No se pudo completar'), self.tr(text), parent=self)
        except queue.Empty:
            pass
        self.poll_timer = self.after(100, self.poll)

    def check_account(self):
        c = self.snapshot()
        if not c['token']:
            self.set_account_status('✕ Introduce el Token de Cuenta para comprobarlo.', 'error')
            self.set_status('Error: falta el Token de Cuenta.', 'error')
            return
        if not valid_token(c['token']):
            self.set_account_status('✕ El token contiene espacios o comillas sueltas. Revisa lo que pegaste.', 'error')
            self.set_status('Error: formato del token inválido.', 'error')
            return
        self.worker(lambda: request(c['token'], c['account_type'], '/users/@me'),
                    lambda data: self.remember_account(data, c['token']), context='account')

    def remember_account(self, data, token):
        if not data.get('username') or not str(data.get('id', '')).isdigit():
            raise ValueError('No se pudo identificar la cuenta. Se detiene el proceso.')
        if normalize_token(self.token.get()) != token:
            raise ValueError('Token cambiado. Vuelve a comprobar la cuenta.')
        self.confirmed_account = dict(username=str(data['username']), id=str(data['id']), token=token)
        return '✓ Token confirmado · @' + data['username']

    def load_package(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(parent=self, title=self.tr('Cargar BAT o ZIP'), filetypes=[(self.tr('Paquetes BAT o ZIP'), '*.bat *.zip')])
        if path:
            self.worker(lambda: import_package(path, DATA.parent / 'imported-images'), self.apply_package)

    def apply_package(self, result):
        c = result['config']
        if c.get('image'):
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('error', Image.DecompressionBombWarning)
                    with Image.open(c['image']) as picture:
                        picture.verify()
            except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
                raise ValueError('La imagen del paquete está dañada. Selecciona otro paquete.') from None
        self.token.set(c['token'])
        self.channel_rows = [dict(row) for row in c['channel_metadata']]
        self.render_channels()
        self.message.delete('1.0', 'end')
        self.message.insert('1.0', c.get('message', ''))
        self.image.set(c.get('image', ''))
        self.minutes.set(str(c['minutes']))
        self.loaded_source = result['source']
        self.set_account_status('Sin comprobar')
        self.language.set(c['language'])
        self.change_language()
        self.refresh_form()
        return 'Paquete cargado. Edita los datos y pulsa Actualizar archivo cargado.'

    def update_loaded(self):
        if self.busy or not self.loaded_source:
            return
        try:
            if self.image.get() and not self.image_valid:
                raise ValueError('La imagen no se pudo abrir. Selecciona una imagen válida antes de generar el ZIP.')
            c = validate(self.snapshot())
        except Exception as exc:
            self.error(exc)
            return
        source = dict(self.loaded_source)
        language = self.language.get()
        def updated(result):
            self.loaded_source = result
            self.refresh_form()
            return ('BAT actualizado. Detén la consola anterior y abre de nuevo el mismo BAT.' if result['kind'] == 'bat' else 'ZIP actualizado. Ya puedes usar el mismo archivo con los nuevos datos.')
        self.worker(lambda: update_package(source, c, BASE, language), updated)

    def export_local(self):
        self.export(local=True)

    def export(self, local=False):
        if self.busy:
            return
        try:
            if self.image.get() and not self.image_valid:
                raise ValueError('La imagen no se pudo abrir. Selecciona una imagen válida antes de generar el ZIP.')
            c = validate(self.snapshot())
        except Exception as exc:
            self.error(exc)
            return
        language = self.language.get()
        if not self.confirmed_account or self.confirmed_account['token'] != c['token']:
            def identified(data):
                self.remember_account(data, c['token'])
                self.set_account_status('✓ Token confirmado · @' + data['username'], 'success')
                self.export_named(c, local, language)
                return 'Procesando…' if self.busy else self.account_source
            self.worker(lambda: request(c['token'], 'personal', '/users/@me'), identified)
            return
        self.export_named(c, local, language)

    def export_named(self, c, local, language):
        c = dict(c, account_username=self.confirmed_account['username'], account_id=self.confirmed_account['id'])
        if local:
            self.worker(lambda: export_local_desktop(c, BASE, language), lambda result: 'BAT creado en el Escritorio: ' + result + '. Ábrelo para iniciar y ver los logs.')
            return
        path = filedialog.asksaveasfilename(parent=self, title=self.tr('Guardar paquete para Discloud'), defaultextension='.zip', initialfile=package_name(c['account_username'], c['account_id']) + '.zip', filetypes=[(self.tr('Paquete ZIP'), '*.zip')])
        if path:
            self.worker(lambda: export_zip(path, c, BASE, language), lambda result: 'ZIP creado: ' + result)

    def destroy(self):
        if hasattr(self, 'poll_timer'):
            self.after_cancel(self.poll_timer)
        super().destroy()

    def close(self):
        if self.busy:
            messagebox.showinfo(self.tr('Operación en curso'), self.tr('Espera a que termine la operación antes de cerrar.'), parent=self)
            return
        if self.snapshot() != self.initial:
            answer = messagebox.askyesnocancel(self.tr('Guardar cambios'), self.tr('Hay cambios sin guardar.\n\nSí: guardar y cerrar.\nNo: descartar los cambios y cerrar.\nCancelar: seguir editando.'), parent=self)
            if answer is None or (answer and not self.save()):
                return
        self.destroy()


if __name__ == '__main__':
    if os.name == 'nt':
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (OSError, AttributeError):
            pass
    App().mainloop()
