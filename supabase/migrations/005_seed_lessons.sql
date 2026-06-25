-- ============================================================
-- Migration 005: lezioni introduttive di esempio (tutti i livelli, vari tipi)
-- Idempotente: si può rilanciare (salta le lezioni già presenti per titolo IT).
-- Eseguire in Supabase SQL Editor DOPO la 003.
-- ============================================================

-- Assicura la colonna livello (se non già aggiunta)
ALTER TABLE academy_lessons ADD COLUMN IF NOT EXISTS level TEXT DEFAULT 'base';

-- 1) FLASHCARD · base
insert into academy_lessons (path_id, type, title, content, sort_order, status, level)
select p.id, 'flashcard',
  $j${"it":"Glossario di base","en":"Basic glossary"}$j$::jsonb,
  $j${"deck":[
    {"term":{"it":"Azione","en":"Stock"},"definition":{"it":"Una quota di proprietà di un'azienda.","en":"A share of ownership in a company."},"example":{"it":"Comprare azioni Apple ti rende socio di Apple.","en":"Buying Apple stock makes you a part-owner of Apple."}},
    {"term":{"it":"ETF","en":"ETF"},"definition":{"it":"Un fondo che replica un indice, scambiato come un'azione.","en":"A fund that tracks an index, traded like a stock."},"example":{"it":"Un ETF sull'S&P 500 contiene 500 aziende.","en":"An S&P 500 ETF holds 500 companies."}},
    {"term":{"it":"Dividendo","en":"Dividend"},"definition":{"it":"Parte degli utili distribuita agli azionisti.","en":"A share of profits paid to shareholders."},"example":{"it":"Coca-Cola paga dividendi ogni trimestre.","en":"Coca-Cola pays dividends every quarter."}},
    {"term":{"it":"Volatilità","en":"Volatility"},"definition":{"it":"Quanto oscilla il prezzo nel tempo.","en":"How much a price swings over time."},"example":{"it":"Le cripto sono molto più volatili dei bond.","en":"Crypto is far more volatile than bonds."}}
  ]}$j$::jsonb,
  1, 'published', 'base'
from academy_paths p where p.slug='le-basi'
and not exists (select 1 from academy_lessons l where l.title->>'it' = 'Glossario di base');

-- 2) SIMULATORE · base
insert into academy_lessons (path_id, type, title, content, sort_order, status, level)
select p.id, 'simulator',
  $j${"it":"La forza dell'interesse composto","en":"The power of compound interest"}$j$::jsonb,
  $j${"model":"compound_interest","teach":{"it":"Più tempo lasci lavorare gli interessi, più cresce l'effetto valanga: gli interessi generano altri interessi.","en":"The longer interest compounds, the bigger the snowball: interest earns more interest."}}$j$::jsonb,
  2, 'published', 'base'
from academy_paths p where p.slug='le-basi'
and not exists (select 1 from academy_lessons l where l.title->>'it' = 'La forza dell''interesse composto');

-- 3) QUIZ · intermedio
insert into academy_lessons (path_id, type, title, content, sort_order, status, level)
select p.id, 'quiz',
  $j${"it":"Rischio e rendimento","en":"Risk and return"}$j$::jsonb,
  $j${"timer_sec":30,"pass_score":70,"questions":[
    {"q":{"it":"In genere, a un rendimento atteso più alto corrisponde...","en":"Generally, a higher expected return comes with..."},"options":[{"it":"Meno rischio","en":"Less risk"},{"it":"Più rischio","en":"More risk"},{"it":"Nessun rischio","en":"No risk"},{"it":"Rendimento garantito","en":"Guaranteed return"}],"correct":1,"explain":{"it":"Rendimento e rischio vanno di pari passo: per puntare a guadagni maggiori accetti oscillazioni maggiori.","en":"Return and risk go together: aiming for higher gains means accepting bigger swings."}},
    {"q":{"it":"Cosa significa avere un orizzonte temporale lungo?","en":"What does a long time horizon mean?"},"options":[{"it":"Investo per pochi giorni","en":"I invest for a few days"},{"it":"Posso aspettare molti anni","en":"I can wait many years"},{"it":"Vendo ogni settimana","en":"I sell every week"},{"it":"Non investo mai","en":"I never invest"}],"correct":1,"explain":{"it":"Con più anni davanti puoi sopportare meglio le oscillazioni di breve periodo.","en":"With more years ahead you can better withstand short-term swings."}}
  ]}$j$::jsonb,
  3, 'published', 'intermedio'
from academy_paths p where p.slug='le-basi'
and not exists (select 1 from academy_lessons l where l.title->>'it' = 'Rischio e rendimento');

-- 4) SCENARIO · intermedio
insert into academy_lessons (path_id, type, title, content, sort_order, status, level)
select p.id, 'scenario',
  $j${"it":"Reagire a una brutta notizia","en":"Reacting to bad news"}$j$::jsonb,
  $j${"start":"n1","ticker":"NVDA","nodes":{
    "n1":{"text":{"it":"Esce una notizia negativa su NVDA e il sentiment crolla in poche ore. Cosa fai?","en":"Bad news hits NVDA and sentiment drops within hours. What do you do?"},"choices":[
      {"label":{"it":"Vendo tutto subito","en":"Sell everything now"},"feedback":{"it":"Reazione di panico: spesso vendere sul calo cristallizza la perdita.","en":"Panic move: selling on the dip often locks in the loss."},"goto":"n2"},
      {"label":{"it":"Controllo le fonti e aspetto","en":"Check the sources and wait"},"feedback":{"it":"Bene: una notizia non fa una tendenza. Valuta i fatti con calma.","en":"Good: one headline isn't a trend. Weigh the facts calmly."},"goto":"n2"}
    ]},
    "n2":{"text":{"it":"Il giorno dopo il prezzo recupera metà del calo. Qual è la lezione?","en":"The next day the price recovers half the drop. What's the lesson?"},"choices":[
      {"label":{"it":"Le emozioni sono cattive consigliere","en":"Emotions are bad advisors"},"feedback":{"it":"Esatto: avere un piano evita decisioni impulsive.","en":"Exactly: having a plan prevents impulsive decisions."},"goto":""}
    ]}
  }}$j$::jsonb,
  4, 'published', 'intermedio'
from academy_paths p where p.slug='le-basi'
and not exists (select 1 from academy_lessons l where l.title->>'it' = 'Reagire a una brutta notizia');

-- 5) SIMULATORE · intermedio
insert into academy_lessons (path_id, type, title, content, sort_order, status, level)
select p.id, 'simulator',
  $j${"it":"L'inflazione che erode","en":"How inflation erodes value"}$j$::jsonb,
  $j${"model":"inflation","teach":{"it":"Con l'inflazione gli stessi euro comprano meno cose negli anni: tenere tutto in liquidità ne erode il valore reale.","en":"With inflation, the same euros buy less over the years: holding only cash erodes real value."}}$j$::jsonb,
  5, 'published', 'intermedio'
from academy_paths p where p.slug='le-basi'
and not exists (select 1 from academy_lessons l where l.title->>'it' = 'L''inflazione che erode');

-- 6) QUIZ · avanzato
insert into academy_lessons (path_id, type, title, content, sort_order, status, level)
select p.id, 'quiz',
  $j${"it":"Diversificazione: oltre i miti","en":"Diversification: beyond the myths"}$j$::jsonb,
  $j${"timer_sec":30,"pass_score":70,"questions":[
    {"q":{"it":"Perché la diversificazione riduce il rischio del portafoglio?","en":"Why does diversification reduce portfolio risk?"},"options":[{"it":"Elimina ogni perdita","en":"It removes all losses"},{"it":"Riduce l'impatto del crollo di un singolo titolo","en":"It lowers the impact of any single holding crashing"},{"it":"Garantisce rendimenti","en":"It guarantees returns"},{"it":"Aumenta sempre i guadagni","en":"It always increases gains"}],"correct":1,"explain":{"it":"Spalmando il capitale su più titoli scorrelati, un singolo crollo pesa meno sul totale.","en":"Spreading capital across uncorrelated holdings means one crash weighs less on the total."}},
    {"q":{"it":"Cosa NON è una vera diversificazione?","en":"What is NOT real diversification?"},"options":[{"it":"Comprare 10 aziende dello stesso settore tech","en":"Buying 10 companies in the same tech sector"},{"it":"Mescolare settori e aree geografiche","en":"Mixing sectors and regions"},{"it":"Aggiungere obbligazioni","en":"Adding bonds"},{"it":"Usare un ETF globale","en":"Using a global ETF"}],"correct":0,"explain":{"it":"Dieci titoli dello stesso settore crollano spesso insieme: è falsa diversificazione.","en":"Ten stocks in the same sector often fall together: that's false diversification."}}
  ]}$j$::jsonb,
  6, 'published', 'avanzato'
from academy_paths p where p.slug='le-basi'
and not exists (select 1 from academy_lessons l where l.title->>'it' = 'Diversificazione: oltre i miti');
