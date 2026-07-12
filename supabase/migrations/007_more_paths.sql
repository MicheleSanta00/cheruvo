-- ============================================================
-- Migration 007: altri percorsi di default (oltre a "Le basi")
-- Idempotente. Eseguire in Supabase SQL Editor dopo la 003/005/006.
-- ============================================================

alter table academy_lessons add column if not exists level text default 'base';

-- ── Percorso: Rischio e mercati ──────────────────────────────
insert into academy_paths (slug, title, description, cover_icon, sort_order, published)
values (
  'rischio-mercati',
  $j${"it":"Rischio e mercati","en":"Risk and markets"}$j$::jsonb,
  $j${"it":"Volatilità, mercati toro e orso, e come gestire il rischio.","en":"Volatility, bull and bear markets, and managing risk."}$j$::jsonb,
  'chart-line', 1, true)
on conflict (slug) do nothing;

insert into academy_lessons (path_id, type, title, content, sort_order, status, level)
select p.id, 'flashcard',
  $j${"it":"Glossario dei mercati","en":"Markets glossary"}$j$::jsonb,
  $j${"deck":[
    {"term":{"it":"Mercato toro","en":"Bull market"},"definition":{"it":"Fase in cui i prezzi salgono a lungo.","en":"A prolonged period of rising prices."},"example":{"it":"Il 2010-2020 è stato un lungo mercato toro.","en":"2010-2020 was a long bull market."}},
    {"term":{"it":"Mercato orso","en":"Bear market"},"definition":{"it":"Prezzi in calo prolungato (di solito -20% o più).","en":"A prolonged fall in prices (usually -20% or more)."},"example":{"it":"Nel 2008 i mercati entrarono in un mercato orso.","en":"In 2008 markets entered a bear market."}},
    {"term":{"it":"Indice","en":"Index"},"definition":{"it":"Un paniere di titoli che misura un mercato.","en":"A basket of securities that measures a market."},"example":{"it":"L'S&P 500 segue 500 grandi aziende USA.","en":"The S&P 500 tracks 500 large US companies."}},
    {"term":{"it":"Liquidità","en":"Liquidity"},"definition":{"it":"Quanto è facile comprare o vendere senza muovere il prezzo.","en":"How easily you can buy or sell without moving the price."},"example":{"it":"Le grandi azioni sono più liquide delle piccole.","en":"Large stocks are more liquid than small ones."}}
  ]}$j$::jsonb, 1, 'published', 'base'
from academy_paths p where p.slug='rischio-mercati'
and not exists (select 1 from academy_lessons l where l.title->>'it' = 'Glossario dei mercati');

insert into academy_lessons (path_id, type, title, content, sort_order, status, level)
select p.id, 'simulator',
  $j${"it":"Investire ogni mese (PAC)","en":"Investing monthly"}$j$::jsonb,
  $j${"model":"pac","teach":{"it":"Versare una piccola somma ogni mese, con costanza, sfrutta tempo e interesse composto senza dover indovinare il momento giusto.","en":"Investing a small amount every month, consistently, harnesses time and compounding without having to time the market."}}$j$::jsonb,
  2, 'published', 'base'
from academy_paths p where p.slug='rischio-mercati'
and not exists (select 1 from academy_lessons l where l.title->>'it' = 'Investire ogni mese (PAC)');

insert into academy_lessons (path_id, type, title, content, sort_order, status, level)
select p.id, 'scenario',
  $j${"it":"Il mercato crolla","en":"The market crashes"}$j$::jsonb,
  $j${"start":"n1","ticker":"SPY","nodes":{
    "n1":{"text":{"it":"I mercati perdono il 15% in una settimana e il tuo portafoglio è in rosso. Cosa fai?","en":"Markets drop 15% in a week and your portfolio is red. What do you do?"},"choices":[
      {"label":{"it":"Vendo tutto per fermare le perdite","en":"Sell everything to stop the losses"},"feedback":{"it":"Vendere nel panico trasforma una perdita sulla carta in una perdita reale.","en":"Panic-selling turns a paper loss into a real one."},"goto":"n2"},
      {"label":{"it":"Mantengo il piano e, se posso, continuo a investire","en":"Stick to the plan and keep investing if I can"},"feedback":{"it":"Storicamente i mercati hanno recuperato: restare investiti premia la pazienza.","en":"Historically markets recovered: staying invested rewards patience."},"goto":"n2"}
    ]},
    "n2":{"text":{"it":"Dopo 12 mesi il mercato è tornato sopra i livelli precedenti. La lezione?","en":"After 12 months the market is back above previous levels. The lesson?"},"choices":[
      {"label":{"it":"Il tempo e la disciplina battono il panico","en":"Time and discipline beat panic"},"feedback":{"it":"Esatto: un piano chiaro evita mosse impulsive.","en":"Exactly: a clear plan prevents impulsive moves."},"goto":""}
    ]}
  }}$j$::jsonb, 3, 'published', 'avanzato'
from academy_paths p where p.slug='rischio-mercati'
and not exists (select 1 from academy_lessons l where l.title->>'it' = 'Il mercato crolla');

-- ── Percorso: Psicologia dell'investitore ────────────────────
insert into academy_paths (slug, title, description, cover_icon, sort_order, published)
values (
  'psicologia',
  $j${"it":"Psicologia dell'investitore","en":"Investor psychology"}$j$::jsonb,
  $j${"it":"I bias e le emozioni che ti costano soldi, e come riconoscerli.","en":"The biases and emotions that cost you money, and how to spot them."}$j$::jsonb,
  'brain', 2, true)
on conflict (slug) do nothing;

insert into academy_lessons (path_id, type, title, content, sort_order, status, level)
select p.id, 'flashcard',
  $j${"it":"Bias ed emozioni","en":"Biases and emotions"}$j$::jsonb,
  $j${"deck":[
    {"term":{"it":"FOMO","en":"FOMO"},"definition":{"it":"La paura di perdere un'occasione, che spinge a comprare sui massimi.","en":"Fear of missing out, pushing you to buy at the top."},"example":{"it":"Comprare una cripto perché 'sta salendo per tutti' è FOMO.","en":"Buying a coin because 'everyone's in' is FOMO."}},
    {"term":{"it":"Panic selling","en":"Panic selling"},"definition":{"it":"Vendere d'impulso durante un crollo.","en":"Impulsively selling during a crash."},"example":{"it":"Vendere tutto nel giorno peggiore è panic selling.","en":"Selling everything on the worst day is panic selling."}},
    {"term":{"it":"Effetto gregge","en":"Herd behavior"},"definition":{"it":"Seguire la folla invece di ragionare sui fatti.","en":"Following the crowd instead of the facts."},"example":{"it":"Comprare solo perché lo fanno tutti.","en":"Buying just because everyone else is."}},
    {"term":{"it":"Avversione alle perdite","en":"Loss aversion"},"definition":{"it":"Una perdita fa più male di quanto un pari guadagno faccia piacere.","en":"A loss hurts more than an equal gain feels good."},"example":{"it":"Tenere un titolo in perdita solo per non 'realizzarla'.","en":"Holding a losing stock just to avoid 'realizing' the loss."}}
  ]}$j$::jsonb, 1, 'published', 'intermedio'
from academy_paths p where p.slug='psicologia'
and not exists (select 1 from academy_lessons l where l.title->>'it' = 'Bias ed emozioni');

insert into academy_lessons (path_id, type, title, content, sort_order, status, level)
select p.id, 'quiz',
  $j${"it":"Riconoscere i bias","en":"Spotting biases"}$j$::jsonb,
  $j${"timer_sec":30,"pass_score":70,"questions":[
    {"q":{"it":"Compri un titolo solo perché 'sta salendo e tutti lo comprano'. Che bias è?","en":"You buy a stock only because 'it's going up and everyone's buying'. Which bias is it?"},"options":[{"it":"Avversione alle perdite","en":"Loss aversion"},{"it":"FOMO / effetto gregge","en":"FOMO / herd behavior"},{"it":"Diversificazione","en":"Diversification"},{"it":"Interesse composto","en":"Compound interest"}],"correct":1,"explain":{"it":"È FOMO unita all'effetto gregge: decisioni guidate dalla folla, non dai fatti.","en":"It's FOMO plus herd behavior: decisions driven by the crowd, not the facts."}},
    {"q":{"it":"Qual è un buon antidoto ai bias emotivi?","en":"What's a good antidote to emotional biases?"},"options":[{"it":"Controllare il portafoglio ogni ora","en":"Checking your portfolio every hour"},{"it":"Avere un piano scritto e regole chiare","en":"Having a written plan and clear rules"},{"it":"Seguire i consigli sui social","en":"Following social media tips"},{"it":"Vendere appena scende","en":"Selling as soon as it drops"}],"correct":1,"explain":{"it":"Un piano deciso a mente fredda ti protegge dalle decisioni impulsive.","en":"A plan set with a cool head protects you from impulsive decisions."}}
  ]}$j$::jsonb, 2, 'published', 'intermedio'
from academy_paths p where p.slug='psicologia'
and not exists (select 1 from academy_lessons l where l.title->>'it' = 'Riconoscere i bias');

insert into academy_lessons (path_id, type, title, content, sort_order, status, level)
select p.id, 'scenario',
  $j${"it":"La FOMO","en":"FOMO"}$j$::jsonb,
  $j${"start":"n1","nodes":{
    "n1":{"text":{"it":"Un'azione è salita del 50% in un mese e tutti online ne parlano. Ti senti in ansia di perderla. Cosa fai?","en":"A stock is up 50% in a month and everyone online is talking about it. You feel anxious about missing out. What do you do?"},"choices":[
      {"label":{"it":"Compro subito con tutto quello che ho","en":"Buy right now with everything I have"},"feedback":{"it":"Classica FOMO: comprare sui massimi per paura porta spesso a comprare caro.","en":"Classic FOMO: buying at the top out of fear often means buying expensive."},"goto":"n2"},
      {"label":{"it":"Mi fermo e studio l'azienda prima di decidere","en":"Pause and research the company before deciding"},"feedback":{"it":"Bene: una decisione informata batte l'impulso.","en":"Good: an informed decision beats impulse."},"goto":"n2"}
    ]},
    "n2":{"text":{"it":"Due settimane dopo l'azione perde il 30%. Cosa hai imparato?","en":"Two weeks later the stock drops 30%. What did you learn?"},"choices":[
      {"label":{"it":"Le decisioni guidate dall'ansia sono rischiose","en":"Anxiety-driven decisions are risky"},"feedback":{"it":"Esatto: rispettare un metodo protegge dai picchi emotivi.","en":"Exactly: sticking to a method protects you from emotional spikes."},"goto":""}
    ]}
  }}$j$::jsonb, 3, 'published', 'intermedio'
from academy_paths p where p.slug='psicologia'
and not exists (select 1 from academy_lessons l where l.title->>'it' = 'La FOMO');
