# AION 2 — Traduzione italiana · Release 1

Traduzione amatoriale gratuita per **AION 2 su Steam, build 26262663**.
153.297 testi italiani. Lingua da selezionare nel gioco: **Español**.

## Scarica e installa

Apri [l’ultima release](https://github.com/Sici29/AION2-Italian-Translation/releases/latest) e scarica **AION2_Italiano_Setup_1.0.0_build26262663.exe**.

1. Chiudi AION 2 e lascia finire gli aggiornamenti Steam.
2. Apri l’installer. La cartella Steam viene cercata automaticamente; puoi indicarla manualmente.
3. Premi **Installare la traduzione**, oppure **Aggiornare la traduzione** se già presente.
4. Nel gioco seleziona **Español**: i testi saranno in italiano.

Lo stesso installer permette di controllare i file e ripristinare gli originali. Conserva il backup automatico. La patch rifiuta una build diversa: dopo un aggiornamento del gioco aspetta una release compatibile.

## Per i revisori

Scarica **AION2_Kit_Revisori_1.0.0_build26262663.zip** ed estrailo in una cartella.
Apri `Laboratorio_Offline.html`, carica `Italiano.json`, cerca e modifica i testi, poi scegli **Salva italiano.json**.
Apri **AION2_Genera_Patch_1.0.0.exe**, seleziona il JSON salvato e genera il nuovo installer. Non occorrono account, server, Python o Node per usare questi due strumenti.
Il generatore conserva numero e ordine delle chiavi e controlla tag, segnaposto, numeri e a capo contro la traduzione di riferimento. Una revisione che richiede una variazione tecnica protetta va verificata dai manutentori prima dell’integrazione.
Per vedere le fonti nel laboratorio offline puoi caricare un `source_catalog.json` estratto dalla tua copia del gioco. Le fonti originali non sono distribuite nel kit.

I sorgenti dell’installer e del generatore sono in `tools/installer`; il testo italiano modificabile è in `payload/italiano.json.gz`. Per lo sviluppo: `python -m pip install -r tools/requirements.txt`. Il codec e il formato del pacchetto sono documentati nel codice. Per rigenerare lo stub usa `python tools/installer/build_stub.py`; quindi il generatore con `--stub` può usare il nuovo stub verificato.

## Verifiche e limiti

La nuova build è stata estratta dagli archivi originali, tradotta e ricontrollata sui testi cambiati. Installazione, rilettura del catalogo, ripristino e download della release hanno verifiche tecniche separate. La revisione umana continua; le questioni senza prove restano aperte. Il gioco non viene avviato automaticamente e questa release non dichiara una verifica completa in gioco.
Il laboratorio privato online è attualmente sospeso: questa distribuzione funziona in locale e non sostituisce la sua cronologia.

## Ringraziamenti

Un ringraziamento speciale ai ragazzi di **LPI** per il loro prezioso aiuto nella revisione della traduzione.

Progetto di [Gioca in Italiano](https://sici29.github.io/gioca-in-italiano/). Traduzione non ufficiale, non affiliata a NCSOFT. AION 2, marchi e immagini del gioco appartengono ai rispettivi titolari. Nessun archivio originale del gioco o credenziale è incluso.
