import os
import re
import traceback
import uuid
from datetime import datetime
from urllib.parse import quote

import requests
from flask import Flask, redirect, render_template_string, request, session, url_for

from gsheet_utils import append_to_sheet


ALLOWED_EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9_.+-]+@((gmail|hotmail|outlook|yahoo)\.(com|com\.br))$",
    re.IGNORECASE,
)
NAME_PATTERN = re.compile(r"[A-Za-z\u00C0-\u00FF '\u00b4`^~.-]+")
VALID_DDDS = {
    "11","12","13","14","15","16","17","18","19",
    "21","22","24","27","28",
    "31","32","33","34","35","37","38",
    "41","42","43","44","45","46","47","48","49",
    "51","53","54","55",
    "61","62","63","64","65","66","67","68","69",
    "71","73","74","75","77","79",
    "81","82","83","84","85","86","87","88","89",
    "91","92","93","94","95","96","97","98","99",
}

LOCAL_OPTIONS = [
    {"id": "1", "nome": "CAJU — SALA 01"},
]

COURSE_CATALOG = [
    {"id": "1", "nome": "ASSISTENTE DE LOGÍSTICA"},
    {"id": "2", "nome": "MARKETING DIGITAL"},
    {"id": "3", "nome": "SOCIAL MEDIA"},
    {"id": "4", "nome": "AUXILIAR ADMINISTRATIVO"},
]

ADDRESS_OPTIONS = {
    "1": "Rua Capit\u00e3o Carlos, n\u00b0 311 - Bonsucesso (Instituto Escrevendo o Futuro da Mar\u00e9)",
}


ADDRESS_OPTIONS = {
    "1": "📍Igreja Pentecostal Da Glória De Deus - Rua Carlos Seidl, nº 1306 - Caju (Em Frente A Praça da Ladeira dos Funcionários).",
}
TURMA_OPTIONS = [
    {
        "id": "1", "curso_id": "1", "local_id": "1",
        "turma_codigo": "ALG-CAJ-01",
        "turma_label": "Seg/Qua — 9h às 11h (início 17/08)",
        "dias_aula": "Segunda e Quarta", "horario": "9h às 11h",
        "data_inicio": "17/08/2026", "encerramento": "16/09/2026",
        "endereco_id": "1",
    },
    {
        "id": "2", "curso_id": "2", "local_id": "1",
        "turma_codigo": "MKD-CAJ-01",
        "turma_label": "Seg/Qua — 18h30 às 20h30 (início 17/08)",
        "dias_aula": "Segunda e Quarta", "horario": "18h30 às 20h30",
        "data_inicio": "17/08/2026", "encerramento": "16/09/2026",
        "endereco_id": "1",
    },
    {
        "id": "3", "curso_id": "3", "local_id": "1",
        "turma_codigo": "SMD-CAJ-01",
        "turma_label": "Ter/Qui — 9h às 11h (início 18/08)",
        "dias_aula": "Terça e Quinta", "horario": "9h às 11h",
        "data_inicio": "18/08/2026", "encerramento": "17/09/2026",
        "endereco_id": "1",
    },
    {
        "id": "4", "curso_id": "4", "local_id": "1",
        "turma_codigo": "ATU-CAJ-01",
        "turma_label": "Sábado — 8h às 12h (início 22/08)",
        "dias_aula": "Sábado", "horario": "8h às 12h",
        "data_inicio": "22/08/2026", "encerramento": "19/09/2026",
        "endereco_id": "1",
    },
]
def build_course_options():
    local_by_id  = {opt["id"]: opt for opt in LOCAL_OPTIONS}
    course_by_id = {opt["id"]: opt for opt in COURSE_CATALOG}
    options = []
    for t in TURMA_OPTIONS:
        local  = local_by_id[t["local_id"]]
        course = course_by_id[t["curso_id"]]
        options.append({
            "id":             t["id"],
            "curso_id":       t["curso_id"],
            "local_id":       t["local_id"],
            "turma_label":    t["turma_label"],
            "local":          local["nome"],
            "curso":          course["nome"],
            "turma":          f"{t['turma_codigo']} - {course['nome']}",
            "dias_aula":      t["dias_aula"],
            "horario":        t["horario"],
            "data_inicio":    t["data_inicio"],
            "encerramento":   t["encerramento"],
            "endereco_curso": ADDRESS_OPTIONS[t["endereco_id"]],
        })
    return options
def build_whatsapp_share_url(home_url):
    message = ("Acabei de me inscrever em uma oportunidade de qualificacao profissional. Confira aqui: " + home_url)
    return f"https://wa.me/?text={quote(message)}"

def get_course_option(option_id):
    return COURSE_OPTIONS_BY_ID.get(str(option_id or ""))

def fill_form_data_from_option(form_data, option):
    form_data["local_id"]       = option["local_id"]
    form_data["curso_id"]       = option["curso_id"]
    form_data["opcao_id"]       = option["id"]
    form_data["local"]          = option["local"]
    form_data["curso"]          = option["curso"]
    form_data["turma"]          = option["turma"]
    form_data["dias_aula"]      = option["dias_aula"]
    form_data["horario"]        = option["horario"]
    form_data["data_inicio"]    = option["data_inicio"]
    form_data["encerramento"]   = option["encerramento"]
    form_data["endereco_curso"] = option["endereco_curso"]

def fill_form_data_from_selection(form_data):
    opcao_id = form_data.get("opcao_id")
    curso_id = form_data.get("curso_id")
    if opcao_id:
        matched = COURSE_OPTIONS_BY_ID.get(str(opcao_id))
        if matched:
            fill_form_data_from_option(form_data, matched)
            return
    if curso_id:
        matched = next(
            (o for o in COURSE_OPTIONS if o["curso_id"] == str(curso_id)),
            None,
        )
        if matched:
            fill_form_data_from_option(form_data, matched)
            return
    for key in ("local", "curso", "turma", "dias_aula", "horario",
                "data_inicio", "encerramento", "endereco_curso", "opcao_id"):
        form_data.setdefault(key, "")

TEMPLATE_WIZARD = r"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>MOVIMENTA RIO — MAR&#201; I E II</title>
    <link rel="stylesheet" href="/static/style.css">
    <link rel="stylesheet" href="/static/assistant.css">
    <link href="https://fonts.googleapis.com/css2?family=Wise:wght@400;700;900&display=swap" rel="stylesheet">
    <script>
        !function(f,b,e,v,n,t,s)
        {if(f.fbq)return;n=f.fbq=function(){n.callMethod?
        n.callMethod.apply(n,arguments):n.queue.push(arguments)};
        if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
        n.queue=[];t=b.createElement(e);t.async=!0;
        t.src=v;s=b.getElementsByTagName(e)[0];
        s.parentNode.insertBefore(t,s)}(window, document,'script',
        'https://connect.facebook.net/en_US/fbevents.js');
        fbq('init', '2008632536670997');
        fbq('track', 'PageView');
    </script>
    <style>
        :root{--cor-principal:#2563eb;--cor-principal-escura:#1d4ed8;--cor-clara:#eff6ff;--cor-texto:#1e3a5f;--cor-borda:#93c5fd;--sombra-card:0 18px 55px rgba(37,99,235,0.18);}
        *{box-sizing:border-box;}html,body{min-height:100%;margin:0;padding:0;}
        body{min-height:100vh;background:radial-gradient(circle at top left,rgba(37,99,235,0.14),transparent 34%),radial-gradient(circle at top right,rgba(147,197,253,0.82),transparent 32%),linear-gradient(135deg,#eff6ff 0%,#fff 42%,#dbeafe 100%);color:var(--cor-texto);font-family:'Wise',Arial,sans-serif;}
        .main-header{border-bottom:4px solid var(--cor-principal);background:rgba(255,255,255,0.92);backdrop-filter:blur(8px);}
        .wizard-page{width:min(900px,98vw);margin:0 auto;padding:8px 0 18px;text-align:center;}
        .wizard-progress{margin:18px auto 22px;padding:18px 18px 20px;border-radius:28px;background:rgba(255,255,255,0.9);box-shadow:0 12px 30px rgba(37,99,235,0.12);}
        .wizard-track{width:100%;height:14px;background:#dbeafe;border-radius:999px;overflow:hidden;}
        .wizard-fill{height:100%;width:25%;background:linear-gradient(90deg,#2563eb 0%,#60a5fa 100%);border-radius:999px;transition:width 0.3s ease;}
        .wizard-labels{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px;}
        .wizard-label{padding:12px 10px;border:1px solid #93c5fd;border-radius:18px;background:#fff;color:#1d4ed8;font-size:0.92rem;font-weight:700;text-align:center;transition:all 0.25s ease;}
        .wizard-label.ativo{border-color:var(--cor-principal);background:var(--cor-clara);color:var(--cor-principal);}
        .wizard-shell{background:rgba(255,255,255,0.88);border:1px solid rgba(255,255,255,0.9);border-radius:34px;box-shadow:var(--sombra-card);overflow:hidden;}
        .wizard-panel{display:none;padding:18px 8px;animation:surgir 0.28s ease;}
        .wizard-panel.ativo{display:block;}
        @keyframes surgir{from{opacity:0;transform:translateY(12px);}to{opacity:1;transform:translateY(0);}}
        .hero-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:14px;align-items:center;justify-items:center;}
        .hero-card{padding:32px;border-radius:30px;background:linear-gradient(135deg,#fff 0%,#eff6ff 58%,#dbeafe 100%);border:1px solid #93c5fd;width:100%;text-align:center;}
        .hero-pill{display:inline-flex;align-items:center;gap:8px;padding:10px 18px;border-radius:999px;background:var(--cor-principal);color:#fff;font-size:0.95rem;font-weight:800;letter-spacing:0.05em;text-transform:uppercase;}
        .hero-title,.panel-title{margin:18px 0 10px;color:var(--cor-principal);font-size:clamp(2rem,3.8vw,3.2rem);line-height:1;letter-spacing:-0.04em;}
        .panel-title{font-size:clamp(1.7rem,3vw,2.4rem);}
        .hero-subtitle,.panel-subtitle{margin:0;color:#1d4ed8;font-size:1.05rem;line-height:1.55;}
        .hero-highlights{display:grid;gap:10px;margin-top:16px;}
        .hero-highlight,.info-card,.review-box,.step-card{border-radius:22px;border:1px solid #bfdbfe;background:#fff;box-shadow:0 8px 24px rgba(37,99,235,0.08);}
        .hero-highlight{padding:12px 14px;color:#1d4ed8;font-size:0.95rem;font-weight:700;}
        .hero-highlight strong{display:block;color:var(--cor-principal);font-size:1.15rem;margin-bottom:4px;}
        .benefits-slider{display:grid;gap:12px;margin-top:8px;}
        .benefits-viewport{position:relative;min-height:76px;overflow:hidden;}
        .benefit-slide{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:10px 12px;border-radius:16px;background:var(--cor-clara);color:var(--cor-principal);font-size:0.98rem;font-weight:800;line-height:1.45;text-align:center;opacity:0;transform:translateX(18px);transition:opacity 0.28s ease,transform 0.28s ease;pointer-events:none;}
        .benefit-slide.ativo{opacity:1;transform:translateX(0);pointer-events:auto;}
        .benefits-controls{display:flex;align-items:center;justify-content:center;gap:10px;}
        .benefits-nav{min-width:44px;min-height:44px;border:none;border-radius:999px;background:#fff;color:var(--cor-principal);box-shadow:0 6px 16px rgba(37,99,235,0.14);font:inherit;font-size:1.1rem;font-weight:900;cursor:pointer;}
        .benefits-dots{display:flex;gap:6px;align-items:center;justify-content:center;}
        .benefits-dot{width:9px;height:9px;border-radius:999px;background:#93c5fd;transition:transform 0.2s ease,background 0.2s ease;}
        .benefits-dot.ativo{background:var(--cor-principal);transform:scale(1.2);}
        .step-card{padding:18px 16px;width:100%;margin:0 auto;text-align:center;}
        .step-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 12px;margin-top:10px;align-items:start;}
        .step-grid.step-grid--stacked{grid-template-columns:minmax(0,1fr);max-width:540px;margin-left:auto;margin-right:auto;}
        .wizard-panel[data-step="dados"] .form-group,.wizard-panel[data-step="escolher"] .form-group{align-items:stretch;text-align:left;}
        .wizard-panel[data-step="dados"] .form-group label,.wizard-panel[data-step="escolher"] .form-group label{width:100%;text-align:left;}
        .wizard-panel[data-step="escolher"] .step-grid.step-grid--stacked{max-width:470px;}
        .wizard-panel[data-step="escolher"] .form-group,.wizard-panel[data-step="escolher"] .form-group.full{width:100%;max-width:100%;}
        .wizard-panel[data-step="escolher"] .input-with-action{width:100%;max-width:100%;}
        .form-group{display:flex;flex-direction:column;gap:4px;width:100%;align-self:start;align-items:center;text-align:center;}
        .form-group.full{grid-column:1/-1;}
        .form-group label,.review-title,.mini-title{color:var(--cor-principal);font-size:1rem;font-weight:800;}
        .form-group input,.form-group select,.form-group textarea{display:block;width:100%!important;max-width:100%!important;min-width:0!important;margin:0!important;box-sizing:border-box;min-height:38px;height:38px;padding:7px 10px;border:1.2px solid var(--cor-borda);border-radius:10px;background:#eff6ff;color:var(--cor-texto);font:inherit;line-height:1.2;text-align:left;outline:none;transition:border-color 0.2s ease,box-shadow 0.2s ease,background 0.2s ease;}
        .form-group select{appearance:none;-webkit-appearance:none;-moz-appearance:none;background-image:url('data:image/svg+xml;utf8,<svg fill="%232563eb" height="20" viewBox="0 0 24 24" width="20" xmlns="http://www.w3.org/2000/svg"><path d="M7 10l5 5 5-5z"/></svg>');background-repeat:no-repeat;background-position:right 14px center;background-size:20px 20px;padding-right:44px;}
        .form-group textarea{min-height:60px;height:auto;resize:vertical;}
        .form-group input:focus,.form-group select:focus,.form-group textarea:focus{border-color:var(--cor-principal);background:#fff;box-shadow:0 0 0 4px rgba(37,99,235,0.12);}
        .readonly-field{background:#eff6ff!important;color:#1d4ed8!important;font-weight:700;}
        .input-with-action{display:grid;grid-template-columns:minmax(0,1fr);gap:10px;align-items:stretch;}
        .input-with-action input{width:100%!important;}
        .icon-button,.cta-button,.secondary-button,.submit-button{border:none;border-radius:18px;font:inherit;font-weight:800;cursor:pointer;transition:transform 0.16s ease,box-shadow 0.16s ease,background 0.16s ease,color 0.16s ease;}
        .icon-button{min-width:56px;min-height:52px;background:var(--cor-principal);color:#fff;box-shadow:0 8px 16px rgba(37,99,235,0.22);}
        .wizard-panel[data-step="escolher"] .icon-button{width:100%!important;min-width:0!important;max-width:100%!important;height:38px!important;min-height:38px!important;padding:0;border-radius:10px;box-shadow:none;}
        .panel-actions .cta-button,.panel-actions .secondary-button,.panel-actions .submit-button{width:100%!important;max-width:100%!important;min-width:0!important;margin:0!important;height:38px;font-size:1rem;}
        .cta-button,.submit-button{background:linear-gradient(90deg,#2563eb 0%,#60a5fa 100%);color:#fff;box-shadow:0 10px 24px rgba(37,99,235,0.24);}
        .secondary-button{background:#fff;color:var(--cor-principal);border:2px solid var(--cor-principal);}
        .cta-button,.secondary-button,.submit-button{min-height:54px;padding:14px 22px;text-transform:uppercase;letter-spacing:0.04em;}
        .cta-button:hover,.secondary-button:hover,.submit-button:hover,.icon-button:hover{transform:translateY(-1px);}
        .panel-actions{display:flex;flex-direction:column-reverse;align-items:center;gap:12px;justify-content:space-between;margin-top:28px;max-width:420px;margin-left:auto;margin-right:auto;}
        .panel-actions>*{flex:1;}
        .balao-erro{margin-top:4px;padding:10px 14px;border-radius:14px;border:1px solid #1d4ed8;background:#2563eb;color:#fff;font-size:0.92rem;font-weight:700;line-height:1.35;}
        .balao-erro[hidden]{display:none;}
        .erro-campo{border-color:#2563eb!important;box-shadow:0 0 0 4px rgba(37,99,235,0.12)!important;}
        .review-layout{display:grid;grid-template-columns:1fr;gap:8px;margin-top:10px;max-width:540px;margin-left:auto;margin-right:auto;}
        .review-box{padding:10px;text-align:center;}
        .review-box.full{grid-column:1/-1;}
        .review-list{display:grid;gap:6px;margin-top:8px;text-align:left;}
        .review-item{display:grid;grid-template-columns:auto 1fr;align-items:center;column-gap:8px;padding:7px 9px;border-radius:10px;background:var(--cor-clara);text-align:left;}
        .review-item strong{color:var(--cor-principal);font-size:0.88rem;white-space:nowrap;}
        .review-item strong::after{content:':';}
        .review-item span{color:var(--cor-texto);font-size:0.94rem;word-break:break-word;text-align:left;}
        .review-check{display:flex;gap:12px;align-items:flex-start;justify-content:flex-start;padding:10px 12px;border-radius:14px;background:var(--cor-clara);color:#1e3a5f;line-height:1.45;text-align:left;}
        .review-check input{margin-top:3px;width:20px;min-width:20px;height:20px;flex:0 0 20px;accent-color:var(--cor-principal);}
        .review-check span{flex:1 1 auto;min-width:0;}
        .review-check ul{margin:8px 0 0 18px;padding:0;list-style-position:outside;text-align:left;}
        .review-box .form-group{align-items:stretch;text-align:left;}
        .review-box .form-group label{width:100%;text-align:left;}
        @media(max-width:860px){.hero-grid,.review-layout{grid-template-columns:1fr;}.step-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;}.step-grid.step-grid--stacked{grid-template-columns:minmax(0,1fr);max-width:540px;}}
        @media(max-width:640px){
            html,body{width:100%!important;max-width:100%!important;overflow-x:hidden!important;}body*{min-width:0;}body{overflow-x:hidden;}
            .main-header{padding:10px 12px;}.header-logos{display:flex;flex-direction:column;align-items:center;gap:10px;}.header-logos img{max-width:min(88vw,280px);height:auto;}
            .wizard-page{width:calc(100% - 8px)!important;max-width:100%!important;padding:4px 0 10px;}
            .wizard-progress,.wizard-panel{width:100%!important;max-width:100%!important;padding:8px;}
            .wizard-labels{grid-template-columns:1fr;gap:6px;}
            .hero-card,.step-card,.review-box{width:100%!important;max-width:100%!important;padding:8px;}
            .input-with-action{grid-template-columns:minmax(0,1fr);width:100%!important;max-width:100%!important;}
            .panel-actions>*{width:100%;}
            .step-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;}
            .step-grid.step-grid--stacked{grid-template-columns:minmax(0,1fr);max-width:100%;}
            .review-layout{grid-template-columns:1fr;max-width:100%;gap:10px;}
            .review-item,.form-group,.form-group input,.form-group select,.form-group textarea,.wizard-shell,.panel-actions,.review-check,.balao-erro{width:100%!important;max-width:100%!important;}
            .form-group label,.review-title,.review-item span,.review-check{word-break:break-word;}
            img,svg{max-width:100%!important;height:auto!important;}
            .form-group input,.form-group select,.form-group textarea,.icon-button{min-height:32px;height:32px;font-size:0.98em;}
            .form-group textarea{min-height:60px;height:auto;}
            .review-check{flex-direction:row;align-items:flex-start;padding:8px;}
            .review-check input{width:22px;min-width:22px;height:22px;flex-basis:22px;}
            .review-check ul{padding-left:2px;}
            .hero-title,.panel-title{font-size:1.3rem;}
            .hero-subtitle,.panel-subtitle{font-size:0.92rem;}
            .wizard-shell{border-radius:16px;}
            .form-group.full{grid-column:auto;}
        }
    </style>
</head>
<body data-start-step="{{ current_step }}">
    <noscript><img height="1" width="1" style="display:none" src="https://www.facebook.com/tr?id=2008632536670997&ev=PageView&noscript=1"/></noscript>
    <script src="/static/assistant.js"></script>
    <header class="main-header">
        <div class="header-logos">
            <img src="/static/logo-prefeitura.png" alt="Prefeitura do Rio" class="logo-prefeitura-topo">
        </div>
    </header>
    <div class="wizard-page">
        <div class="wizard-progress">
            <div class="wizard-track"><div class="wizard-fill" id="wizard-fill"></div></div>
            <div class="wizard-labels">
                <div class="wizard-label" data-step-label="index">1. In&#237;cio</div>
                <div class="wizard-label" data-step-label="dados">2. Dados pessoais</div>
                <div class="wizard-label" data-step-label="escolher">3. Escolher</div>
                <div class="wizard-label" data-step-label="revisao">4. Revis&#227;o</div>
            </div>
        </div>
        <div class="wizard-shell">
            <form id="wizard-form" method="POST" action="{{ url_for('inscricao_unica') }}" autocomplete="off" novalidate>

                <!-- PASSO 1 -->
                <section class="wizard-panel" data-step="index">
                    <div class="hero-grid"><div class="hero-card">
                        <span class="hero-pill">PROJETO: MOVIMENTA RIO</span>
                        <h1 class="hero-title">CURSOS GRATUITOS EM MAR&#201; I E II</h1>
                        <p class="hero-subtitle">Programa Movimenta Rio &bull; Prefeitura do Rio de Janeiro. Garanta sua vaga e transforme sua carreira!</p>
                        <div class="hero-highlights">
                            <div class="hero-highlight" style="text-align:left;">
                                <strong style="display:block;text-align:center;">CURSOS DISPON&#205;VEIS:</strong>
                                &#129302; INTELIG&#202;NCIA ARTIFICIAL<br>
                                &#128218; GERENCIAMENTO DE TR&#193;FEGO PAGO<br>
                                &#128241; MARKETING DIGITAL<br>
                                &#128218; SOCIAL MEDIA<br>
                                &#128194; AUXILIAR ADMINISTRATIVO
                            </div>
                            <div class="hero-highlight">
                                <strong>BENEF&#205;CIOS</strong>
                                <div class="benefits-slider" data-benefits-slider>
                                    <div class="benefits-viewport">
                                        <div class="benefit-slide ativo">100% Gratuito</div>
                                        <div class="benefit-slide">&#127891; Certificado de Conclus&#227;o</div>
                                        <div class="benefit-slide">&#128218; Material Did&#225;tico Incluso</div>
                                    </div>
                                    <div class="benefits-controls">
                                        <button type="button" class="benefits-nav" data-benefits-prev aria-label="Benef&#237;cio anterior">&#8249;</button>
                                        <div class="benefits-dots" data-benefits-dots></div>
                                        <button type="button" class="benefits-nav" data-benefits-next aria-label="Pr&#243;ximo benef&#237;cio">&#8250;</button>
                                    </div>
                                </div>
                            </div>
                            <div class="hero-highlight">
                                <strong>MOVIMENTA RIO</strong>
                                Qualifica&#231;&#227;o profissional gratuita para ampliar suas oportunidades e fortalecer sua entrada no mercado de trabalho.
                            </div>
                        </div>
                        <div class="panel-actions">
                            <button type="button" class="cta-button" data-next="dados">Come&#231;ar inscri&#231;&#227;o</button>
                        </div>
                    </div></div>
                </section>

                <!-- PASSO 2 -->
                <section class="wizard-panel" data-step="dados">
                    <div class="step-card">
                        <h2 class="panel-title">Dados pessoais</h2>
                        <div class="step-grid step-grid--stacked">
                            <div class="form-group full"><label for="nome">Nome completo *</label><input type="text" id="nome" name="nome" maxlength="50" placeholder="Digite seu nome completo" value="{{ form_data.get('nome','') }}"><div class="balao-erro" id="nome-error" {% if not errors.get('nome') %}hidden{% endif %}>{{ errors.get('nome','') }}</div></div>
                            <div class="form-group"><label for="genero">G&#234;nero *</label><select id="genero" name="genero"><option value="">Selecione</option>{% for genero in generos %}<option value="{{ genero }}" {% if form_data.get('genero')==genero %}selected{% endif %}>{{ genero }}</option>{% endfor %}</select><div class="balao-erro" id="genero-error" {% if not errors.get('genero') %}hidden{% endif %}>{{ errors.get('genero','') }}</div></div>
                            <div class="form-group"><label for="cpf">CPF *</label><input type="text" id="cpf" name="cpf" maxlength="14" placeholder="000.000.000-00" value="{{ form_data.get('cpf','') }}"><div class="balao-erro" id="cpf-error" {% if not errors.get('cpf') %}hidden{% endif %}>{{ errors.get('cpf','') }}</div></div>
                            <div class="form-group"><label for="nascimento">Data de nascimento *</label><input type="text" id="nascimento" name="nascimento" maxlength="10" placeholder="dd/mm/aaaa" value="{{ form_data.get('nascimento','') }}"><div class="balao-erro" id="nascimento-error" {% if not errors.get('nascimento') %}hidden{% endif %}>{{ errors.get('nascimento','') }}</div></div>
                            <div class="form-group"><label for="whatsapp">WhatsApp *</label><input type="text" id="whatsapp" name="whatsapp" maxlength="16" placeholder="(00) 00000-0000" value="{{ form_data.get('whatsapp','') }}"><div class="balao-erro" id="whatsapp-error" {% if not errors.get('whatsapp') %}hidden{% endif %}>{{ errors.get('whatsapp','') }}</div></div>
                            <div class="form-group"><label for="cep">CEP *</label><input type="text" id="cep" name="cep" maxlength="9" placeholder="00000-000" value="{{ form_data.get('cep','') }}"><div class="balao-erro" id="cep-error" {% if not errors.get('cep') %}hidden{% endif %}>{{ errors.get('cep','') }}</div></div>
                            <div class="form-group"><label for="bairro">Bairro *</label><input type="text" id="bairro" name="bairro" maxlength="40" placeholder="Nome do bairro" value="{{ form_data.get('bairro','') }}"><div class="balao-erro" id="bairro-error" {% if not errors.get('bairro') %}hidden{% endif %}>{{ errors.get('bairro','') }}</div></div>
                            <div class="form-group full"><label for="email">E-mail *</label><input type="email" id="email" name="email" maxlength="60" placeholder="seuemail@gmail.com" value="{{ form_data.get('email','') }}"><div class="balao-erro" id="email-error" {% if not errors.get('email') %}hidden{% endif %}>{{ errors.get('email','') }}</div></div>
                        </div>
                        <div class="panel-actions">
                            <button type="button" class="secondary-button" data-prev="index">Voltar</button>
                            <button type="button" class="cta-button" data-next="escolher">Pr&#243;ximo</button>
                        </div>
                    </div>
                </section>

                <!-- PASSO 3 -->
                <section class="wizard-panel" data-step="escolher">
                    <div class="step-card">
                        <h2 class="panel-title">Escolha seu curso</h2>
                        <div class="step-grid step-grid--stacked">
                            <div class="form-group full"><label for="curso_id">Curso *</label><select id="curso_id" name="curso_id"><option value="">Selecione um curso</option>{% for curso in course_catalog %}<option value="{{ curso.id }}" {% if form_data.get('curso_id')==curso.id %}selected{% endif %}>{{ curso.nome }}</option>{% endfor %}</select><div class="balao-erro" id="curso_id-error" {% if not errors.get('curso_id') %}hidden{% endif %}>{{ errors.get('curso_id','') }}</div></div>
                            <div class="form-group full" id="local-group" style="display:none;"><label for="local_id_select">Local *</label><select id="local_id_select"><option value="">Selecione um local</option></select><div class="balao-erro" id="local_id-error" hidden></div></div>
                            <div class="form-group full" id="turma-group" style="display:none;"><label for="opcao_id_select">Hor&#225;rio *</label><select id="opcao_id_select"><option value="">Selecione um hor&#225;rio</option></select><div class="balao-erro" id="opcao_id-error" hidden></div></div>
                            <input type="hidden" id="opcao_id" name="opcao_id" value="{{ form_data.get('opcao_id','') }}">
                            <input type="hidden" id="local_id" name="local_id" value="{{ form_data.get('local_id','') }}">
                            <input type="hidden" id="local"    name="local"    value="{{ form_data.get('local','') }}">
                            <input type="hidden" id="curso"    name="curso"    value="{{ form_data.get('curso','') }}">
                            <input type="hidden" id="turma"    name="turma"    value="{{ form_data.get('turma','') }}">
                            <div class="form-group full" id="info-local-group" style="display:none;"><label for="local_display">LOCAL SELECIONADO</label><input type="text" id="local_display" class="readonly-field" readonly value="{{ form_data.get('local','') }}"></div>
                            <div class="form-group" id="info-dias-group" style="display:none;"><label for="dias_aula">DIA DE AULA</label><input type="text" id="dias_aula" name="dias_aula" class="readonly-field" readonly value="{{ form_data.get('dias_aula','') }}"></div>
                            <div class="form-group" id="info-horario-group" style="display:none;"><label for="horario">HOR&#193;RIO</label><input type="text" id="horario" name="horario" class="readonly-field" readonly value="{{ form_data.get('horario','') }}"></div>
                            <div class="form-group" id="info-inicio-group" style="display:none;"><label for="data_inicio">DATA DE IN&#205;CIO</label><input type="text" id="data_inicio" name="data_inicio" class="readonly-field" readonly value="{{ form_data.get('data_inicio','') }}"></div>
                            <div class="form-group" id="info-enc-group" style="display:none;"><label for="encerramento">ENCERRAMENTO</label><input type="text" id="encerramento" name="encerramento" class="readonly-field" readonly value="{{ form_data.get('encerramento','') }}"></div>
                            <div class="form-group full" id="info-endereco-group" style="display:none;"><label for="endereco_curso">ENDERE&#199;O</label><div class="input-with-action"><input type="text" id="endereco_curso" name="endereco_curso" class="readonly-field" readonly value="{{ form_data.get('endereco_curso','') }}"><button type="button" class="icon-button" id="btn-copiar-endereco" title="Copiar endere&#231;o">COPIAR &#128203;</button></div></div>
                        </div>
                        <div class="panel-actions">
                            <button type="button" class="secondary-button" data-prev="dados">Voltar</button>
                            <button type="button" class="cta-button" data-next="revisao">Ir para revis&#227;o</button>
                        </div>
                    </div>
                </section>

                <!-- PASSO 4 -->
                <section class="wizard-panel" data-step="revisao">
                    <div class="step-card">
                        <h2 class="panel-title">Revise antes de finalizar</h2>
                        <p class="panel-subtitle">Confira os dados preenchidos e confirme sua participa&#231;&#227;o.</p>
                        <div class="review-layout">
                            <div class="review-box"><div class="review-title">Dados pessoais</div><div class="review-list">
                                <div class="review-item"><strong>Nome</strong><span data-review="nome"></span></div>
                                <div class="review-item"><strong>CPF</strong><span data-review="cpf"></span></div>
                                <div class="review-item"><strong>Nascimento</strong><span data-review="nascimento"></span></div>
                                <div class="review-item"><strong>G&#234;nero</strong><span data-review="genero"></span></div>
                                <div class="review-item"><strong>WhatsApp</strong><span data-review="whatsapp"></span></div>
                                <div class="review-item"><strong>CEP</strong><span data-review="cep"></span></div>
                                <div class="review-item"><strong>Bairro</strong><span data-review="bairro"></span></div>
                                <div class="review-item"><strong>E-mail</strong><span data-review="email"></span></div>
                            </div></div>
                            <div class="review-box"><div class="review-title">Informa&#231;&#245;es do curso</div><div class="review-list">
                                <div class="review-item"><strong>Curso</strong><span data-review="curso_nome"></span></div>
                                <div class="review-item"><strong>Local</strong><span data-review="local_nome"></span></div>
                                <div class="review-item"><strong>Dia</strong><span data-review="dias_aula"></span></div>
                                <div class="review-item"><strong>Hor&#225;rio</strong><span data-review="horario"></span></div>
                                <div class="review-item"><strong>In&#237;cio</strong><span data-review="data_inicio"></span></div>
                                <div class="review-item"><strong>Encerramento</strong><span data-review="encerramento"></span></div>
                                <div class="review-item"><strong>Endere&#231;o</strong><span data-review="endereco_curso"></span></div>
                            </div></div>
                            <div class="review-box full"><div class="form-group"><label for="como_conheceu">Como conheceu (opcional)</label><input type="text" id="como_conheceu" name="como_conheceu" maxlength="120" placeholder="Digite como conheceu o projeto" value="{{ form_data.get('como_conheceu','') }}"></div></div>
                            <div class="review-box full">
                                <div style="margin-bottom:10px;color:#1d4ed8;font-size:0.98rem;text-align:left;"><strong>Elegibilidade:</strong> Este curso &#233; destinado a pessoas com 16 anos ou mais.</div>
                                <label class="review-check" for="confirma_dados">
                                    <input type="checkbox" id="confirma_dados" name="confirma_dados" value="sim" {% if form_data.get('confirma_dados') %}checked{% endif %}>
                                    <span>Confirmo que tenho 16 anos ou mais e interesse em participar do curso selecionado.<br>Todas as informa&#231;&#245;es fornecidas s&#227;o verdadeiras e estou de acordo com os termos de participa&#231;&#227;o.<br>Autorizo o uso dos meus dados para fins de inscri&#231;&#227;o e contato relacionado ao curso.<br>Tamb&#233;m autorizo o uso da minha imagem para divulga&#231;&#227;o nos canais do projeto e da Prefeitura do Rio de Janeiro.</span>
                                </label>
                                <div style="margin-top:10px;color:#1d4ed8;font-size:0.95rem;text-align:left;"><strong>Ao confirmar voc&#234; declara ci&#234;ncia de que:</strong><ul><li>O curso &#233; totalmente gratuito</li><li>Os dados ser&#227;o usados apenas para inscri&#231;&#227;o</li></ul></div>
                                <div class="balao-erro" id="confirma_dados-error" {% if not errors.get('confirma_dados') %}hidden{% endif %}>{{ errors.get('confirma_dados','') }}</div>
                            </div>
                        </div>
                        <div class="panel-actions">
                            <button type="button" class="secondary-button" data-prev="escolher">Voltar</button>
                            <button type="submit" class="submit-button">Finalizar inscri&#231;&#227;o</button>
                        </div>
                    </div>
                </section>
            </form>
        </div>
    </div>
    <script>
        document.addEventListener('DOMContentLoaded', function () {
            var stepOrder=['index','dados','escolher','revisao'];
            var progressByStep={index:25,dados:45,escolher:70,revisao:90};
            var form=document.getElementById('wizard-form'),fill=document.getElementById('wizard-fill');
            var startStep=document.body.dataset.startStep||'index';
            var panels=Array.from(document.querySelectorAll('[data-step]'));
            var labels=Array.from(document.querySelectorAll('[data-step-label]'));
            var reviewTargets=Array.from(document.querySelectorAll('[data-review]'));
            var benefitsSliders=Array.from(document.querySelectorAll('[data-benefits-slider]'));
            var courseOptions={{ course_options|tojson }};
            var localOptions={{ local_options|tojson }};
            var courseOptionsById=Object.fromEntries(courseOptions.map(function(o){return[String(o.id),o];}));
            var nomeInput=document.getElementById('nome'),generoInput=document.getElementById('genero'),cpfInput=document.getElementById('cpf'),nascimentoInput=document.getElementById('nascimento'),whatsappInput=document.getElementById('whatsapp'),cepInput=document.getElementById('cep'),bairroInput=document.getElementById('bairro'),emailInput=document.getElementById('email'),confirmaDadosInput=document.getElementById('confirma_dados');
            var courseSelect=document.getElementById('curso_id'),localSelectEl=document.getElementById('local_id_select'),opcaoSelectEl=document.getElementById('opcao_id_select'),localGroup=document.getElementById('local-group'),turmaGroup=document.getElementById('turma-group'),opcaoIdInput=document.getElementById('opcao_id'),localIdInput=document.getElementById('local_id'),localInput=document.getElementById('local'),localDisplay=document.getElementById('local_display'),cursoInput=document.getElementById('curso'),turmaInput=document.getElementById('turma'),diasAulaInput=document.getElementById('dias_aula'),horarioInput=document.getElementById('horario'),dataInicioInput=document.getElementById('data_inicio'),encerramentoInput=document.getElementById('encerramento'),enderecoInput=document.getElementById('endereco_curso'),btnCopiarEndereco=document.getElementById('btn-copiar-endereco');
            var infoLocalGroup=document.getElementById('info-local-group'),infoDiasGroup=document.getElementById('info-dias-group'),infoHorarioGroup=document.getElementById('info-horario-group'),infoInicioGroup=document.getElementById('info-inicio-group'),infoEncGroup=document.getElementById('info-enc-group'),infoEndGroup=document.getElementById('info-endereco-group');
            function somenteDigitos(v){return(v||'').replace(/\D/g,'');}
            function setError(id,msg){var f=document.getElementById(id),e=document.getElementById(id+'-error');if(f)f.classList.toggle('erro-campo',Boolean(msg));if(e){e.textContent=msg||'';e.hidden=!msg;}}
            function mostrarInfoCurso(show){[infoLocalGroup,infoDiasGroup,infoHorarioGroup,infoInicioGroup,infoEncGroup,infoEndGroup].forEach(function(el){if(el)el.style.display=show?'':'none';});}
            function aplicarOpcao(opcaoId){var op=courseOptionsById[String(opcaoId||'')];if(!op){opcaoIdInput.value='';localIdInput.value='';localInput.value='';if(localDisplay)localDisplay.value='';cursoInput.value='';turmaInput.value='';diasAulaInput.value='';horarioInput.value='';dataInicioInput.value='';encerramentoInput.value='';enderecoInput.value='';mostrarInfoCurso(false);return;}opcaoIdInput.value=op.id;localIdInput.value=op.local_id;localInput.value=op.local;if(localDisplay)localDisplay.value=op.local;cursoInput.value=op.curso;turmaInput.value=op.turma;diasAulaInput.value=op.dias_aula;horarioInput.value=op.horario;dataInicioInput.value=op.data_inicio;encerramentoInput.value=op.encerramento;enderecoInput.value=op.endereco_curso;mostrarInfoCurso(true);setError('curso_id','');setError('opcao_id','');syncReview();}
            function atualizarLocaisPorCurso(cursoId,selectedLocalId,selectedOpcaoId){var turmasDoCurso=courseOptions.filter(function(o){return String(o.curso_id)===String(cursoId||'');});var localIdsUsados=[],locaisUnicos=[];turmasDoCurso.forEach(function(o){if(localIdsUsados.indexOf(o.local_id)===-1){localIdsUsados.push(o.local_id);var l=localOptions.find(function(x){return String(x.id)===String(o.local_id);});if(l)locaisUnicos.push(l);}});localSelectEl.innerHTML='';opcaoSelectEl.innerHTML='';turmaGroup.style.display='none';aplicarOpcao('');if(locaisUnicos.length===0){localGroup.style.display='none';return;}localGroup.style.display='';var ph=document.createElement('option');ph.value='';ph.textContent='Selecione um local';localSelectEl.appendChild(ph);locaisUnicos.forEach(function(loc){var opt=document.createElement('option');opt.value=loc.id;opt.textContent=loc.nome;if(String(loc.id)===String(selectedLocalId||''))opt.selected=true;localSelectEl.appendChild(opt);});if(locaisUnicos.length===1&&!selectedLocalId){localSelectEl.value=locaisUnicos[0].id;atualizarHorariosPorLocal(cursoId,locaisUnicos[0].id,selectedOpcaoId);return;}if(selectedLocalId&&localIdsUsados.indexOf(String(selectedLocalId))!==-1){atualizarHorariosPorLocal(cursoId,selectedLocalId,selectedOpcaoId);}}
            function atualizarHorariosPorLocal(cursoId,localId,selectedOpcaoId){var turmas=courseOptions.filter(function(o){return String(o.curso_id)===String(cursoId||'')&&String(o.local_id)===String(localId||'');});opcaoSelectEl.innerHTML='';if(turmas.length===0){turmaGroup.style.display='none';aplicarOpcao('');return;}turmaGroup.style.display='';var ph=document.createElement('option');ph.value='';ph.textContent='Selecione um hor\u00e1rio';opcaoSelectEl.appendChild(ph);turmas.forEach(function(op){var opt=document.createElement('option');opt.value=op.id;opt.textContent=op.dias_aula+' | '+op.horario;if(String(op.id)===String(selectedOpcaoId||''))opt.selected=true;opcaoSelectEl.appendChild(opt);});if(selectedOpcaoId&&turmas.some(function(o){return String(o.id)===String(selectedOpcaoId);})){aplicarOpcao(selectedOpcaoId);}else if(turmas.length===1){opcaoSelectEl.value=turmas[0].id;aplicarOpcao(turmas[0].id);}else{aplicarOpcao('');}}
            courseSelect.addEventListener('change',function(){setError('curso_id','');var c=courseSelect.value;if(c){atualizarLocaisPorCurso(c,'','');}else{localGroup.style.display='none';turmaGroup.style.display='none';aplicarOpcao('');}syncReview();});
            localSelectEl.addEventListener('change',function(){setError('local_id','');var l=localSelectEl.value;if(l&&courseSelect.value){atualizarHorariosPorLocal(courseSelect.value,l,'');}else{turmaGroup.style.display='none';aplicarOpcao('');}syncReview();});
            opcaoSelectEl.addEventListener('change',function(){setError('opcao_id','');aplicarOpcao(opcaoSelectEl.value);});
            if(btnCopiarEndereco&&enderecoInput){btnCopiarEndereco.addEventListener('click',function(){navigator.clipboard.writeText(enderecoInput.value).then(function(){btnCopiarEndereco.textContent='COPIADO \u2705';}).catch(function(){enderecoInput.select();document.execCommand('copy');btnCopiarEndereco.textContent='COPIADO \u2705';});setTimeout(function(){btnCopiarEndereco.textContent='COPIAR 📋';},1200);});}
            function mostrarPasso(step){panels.forEach(function(p){p.classList.toggle('ativo',p.dataset.step===step);});labels.forEach(function(l){l.classList.toggle('ativo',l.dataset.stepLabel===step);});fill.style.width=(progressByStep[step]||25)+'%';window.scrollTo({top:0,behavior:'smooth'});}
            function syncReview(){reviewTargets.forEach(function(t){var key=t.dataset.review;if(key==='curso_nome'){t.textContent=cursoInput?cursoInput.value.trim():'';return;}if(key==='local_nome'){t.textContent=localInput?localInput.value.trim():'';return;}var f=document.getElementById(key);if(!f){t.textContent='';return;}if(f.tagName==='SELECT'){var s=f.options[f.selectedIndex];t.textContent=s?s.text.trim():'';}else{t.textContent=f.value.trim();}});}
            function validarCPF(cpf){var d=somenteDigitos(cpf);if(d.length!==11||/^(\d)\1+$/.test(d))return false;var s=0,g;for(var i=0;i<9;i++)s+=Number(d[i])*(10-i);g=(s*10)%11;if(g===10)g=0;if(g!==Number(d[9]))return false;s=0;for(var i=0;i<10;i++)s+=Number(d[i])*(11-i);g=(s*10)%11;if(g===10)g=0;return g===Number(d[10]);}
            function validarEmail(e){return/^[a-zA-Z0-9_.+-]+@((gmail|hotmail|outlook|yahoo)\.(com|com\.br))$/i.test((e||'').trim());}
            function idadePermitida(v){var p=(v||'').split('/');if(p.length!==3)return false;var d=new Date(Number(p[2]),Number(p[1])-1,Number(p[0]));if(isNaN(d.getTime())||d.getDate()!==Number(p[0])||d.getMonth()!==Number(p[1])-1)return false;var h=new Date();var i=h.getFullYear()-d.getFullYear();if(h.getMonth()-d.getMonth()<0||(h.getMonth()===d.getMonth()&&h.getDate()<d.getDate()))i--;return i>=16&&i<=90;}
            function validarDDD(w){var d=somenteDigitos(w);if(d.length<11)return false;return['11','12','13','14','15','16','17','18','19','21','22','24','27','28','31','32','33','34','35','37','38','41','42','43','44','45','46','47','48','49','51','53','54','55','61','62','63','64','65','66','67','68','69','71','73','74','75','77','79','81','82','83','84','85','86','87','88','89','91','92','93','94','95','96','97','98','99'].includes(d.slice(0,2));}
            function mascCPF(){var v=somenteDigitos(cpfInput.value).slice(0,11);if(v.length>9)v=v.replace(/(\d{3})(\d{3})(\d{3})(\d{1,2})/,'$1.$2.$3-$4');else if(v.length>6)v=v.replace(/(\d{3})(\d{3})(\d{1,3})/,'$1.$2.$3');else if(v.length>3)v=v.replace(/(\d{3})(\d{1,3})/,'$1.$2');cpfInput.value=v;}
            function mascNasc(){var v=somenteDigitos(nascimentoInput.value).slice(0,8);if(v.length>4)v=v.replace(/(\d{2})(\d{2})(\d{1,4})/,'$1/$2/$3');else if(v.length>2)v=v.replace(/(\d{2})(\d{1,2})/,'$1/$2');nascimentoInput.value=v;}
            function mascWpp(){var v=somenteDigitos(whatsappInput.value).slice(0,11);if(v.length>6)v=v.replace(/(\d{2})(\d{5})(\d{0,4})/,'($1) $2-$3');else if(v.length>2)v=v.replace(/(\d{2})(\d{1,5})/,'($1) $2');whatsappInput.value=v;}
            function mascCep(){var v=somenteDigitos(cepInput.value).slice(0,8);if(v.length>5)v=v.replace(/(\d{5})(\d{1,3})/,'$1-$2');cepInput.value=v;}
            function vNome(){var v=nomeInput.value.trim();if(!v){setError('nome','Digite seu nome completo.');return false;}if(v.length>50){setError('nome','M\u00e1ximo 50 caracteres.');return false;}if(!/^[A-Za-z\u00C0-\u00FF '\u00b4`^~.-]+$/.test(v)){setError('nome','Use apenas letras e sinais permitidos.');return false;}setError('nome','');return true;}
            function vGenero(){if(!generoInput.value){setError('genero','Selecione o g\u00eanero.');return false;}setError('genero','');return true;}
            function vCPF(){if(!validarCPF(cpfInput.value)){setError('cpf','CPF inv\u00e1lido.');return false;}setError('cpf','');return true;}
            function vNasc(){if(!idadePermitida(nascimentoInput.value)){setError('nascimento','Idade permitida: 16 a 90 anos.');return false;}setError('nascimento','');return true;}
            function vWpp(){var d=somenteDigitos(whatsappInput.value);if(d.length!==11||!/^\(\d{2}\) \d{5}-\d{4}$/.test(whatsappInput.value)||!validarDDD(whatsappInput.value)){setError('whatsapp','Informe um WhatsApp com DDD v\u00e1lido do Brasil.');return false;}setError('whatsapp','');return true;}
            function vCep(){if(!/^\d{5}-\d{3}$/.test(cepInput.value.trim())){setError('cep','CEP inv\u00e1lido. Formato: 00000-000.');return false;}setError('cep','');return true;}
            function vBairro(){var v=bairroInput.value.trim();if(!v){setError('bairro','Informe o bairro.');return false;}if(v.length>40){setError('bairro','M\u00e1ximo 40 caracteres.');return false;}setError('bairro','');return true;}
            function vEmail(){if(!validarEmail(emailInput.value)){setError('email','E-mail inv\u00e1lido. Use Gmail, Hotmail, Outlook ou Yahoo.');return false;}setError('email','');return true;}
            function validarPassoDados(){var checks=[{ok:vNome(),f:nomeInput},{ok:vGenero(),f:generoInput},{ok:vCPF(),f:cpfInput},{ok:vNasc(),f:nascimentoInput},{ok:vWpp(),f:whatsappInput},{ok:vCep(),f:cepInput},{ok:vBairro(),f:bairroInput},{ok:vEmail(),f:emailInput}];var first=checks.find(function(c){return!c.ok;});if(first){first.f.focus();return false;}return true;}
            function validarPassoEscolher(){if(!courseSelect.value){setError('curso_id','Selecione um curso.');courseSelect.focus();return false;}if(localGroup.style.display!=='none'&&!localSelectEl.value){setError('local_id','Selecione um local.');localSelectEl.focus();return false;}if(turmaGroup.style.display!=='none'&&!opcaoSelectEl.value){setError('opcao_id','Selecione um hor\u00e1rio.');opcaoSelectEl.focus();return false;}if(!opcaoIdInput.value){setError('curso_id','N\u00e3o foi poss\u00edvel determinar a turma. Tente novamente.');return false;}return true;}
            function validarPassoRevisao(){if(!confirmaDadosInput.checked){setError('confirma_dados','Confirme os dados para finalizar.');confirmaDadosInput.focus();return false;}setError('confirma_dados','');return true;}
            async function buscarBairro(){var limpo=somenteDigitos(cepInput.value);if(limpo.length!==8)return;try{var r=await fetch('https://viacep.com.br/ws/'+limpo+'/json/');var d=await r.json();if(!d.erro&&d.bairro){bairroInput.value=d.bairro;vBairro();syncReview();}}catch(e){console.error(e);}}
            document.querySelectorAll('[data-next]').forEach(function(btn){btn.addEventListener('click',function(){var t=btn.dataset.next;if(t==='escolher'&&!validarPassoDados())return;if(t==='revisao'&&!validarPassoEscolher())return;syncReview();mostrarPasso(t);});});
            document.querySelectorAll('[data-prev]').forEach(function(btn){btn.addEventListener('click',function(){syncReview();mostrarPasso(btn.dataset.prev);});});
            form.addEventListener('submit',function(e){if(!validarPassoDados()){e.preventDefault();mostrarPasso('dados');return;}syncReview();if(!validarPassoRevisao()){e.preventDefault();mostrarPasso('revisao');}});
            nomeInput.addEventListener('blur',vNome);generoInput.addEventListener('change',vGenero);
            cpfInput.addEventListener('input',function(){mascCPF();if(somenteDigitos(cpfInput.value).length===11)vCPF();else setError('cpf','');syncReview();});
            nascimentoInput.addEventListener('input',function(){mascNasc();syncReview();});nascimentoInput.addEventListener('blur',vNasc);
            whatsappInput.addEventListener('input',function(){mascWpp();if(somenteDigitos(whatsappInput.value).length>=10)vWpp();else setError('whatsapp','');syncReview();});
            cepInput.addEventListener('input',function(){mascCep();bairroInput.value='';if(cepInput.value.length===9){vCep();buscarBairro();}else setError('cep','');syncReview();});
            bairroInput.addEventListener('blur',function(){vBairro();syncReview();});
            emailInput.addEventListener('input',function(){if(emailInput.value.trim())vEmail();else setError('email','');syncReview();});
            confirmaDadosInput.addEventListener('change',function(){if(confirmaDadosInput.checked)setError('confirma_dados','');});
            ['nome','genero','whatsapp','cep','bairro','email','curso_id','como_conheceu'].forEach(function(id){var f=document.getElementById(id);if(f){f.addEventListener('input',syncReview);f.addEventListener('change',syncReview);}});
            function initBenefitsSlider(slider){var slides=Array.from(slider.querySelectorAll('.benefit-slide')),dotsHost=slider.querySelector('[data-benefits-dots]'),prevBtn=slider.querySelector('[data-benefits-prev]'),nextBtn=slider.querySelector('[data-benefits-next]');if(!slides.length||!dotsHost||!prevBtn||!nextBtn)return;var cur=Math.max(slides.findIndex(function(s){return s.classList.contains('ativo');}),0),timer;var dots=slides.map(function(_,i){var dot=document.createElement('button');dot.type='button';dot.className='benefits-dot';dot.setAttribute('aria-label','Benef\u00edcio '+(i+1));dot.addEventListener('click',function(){show(i);restart();});dotsHost.appendChild(dot);return dot;});function show(i){cur=(i+slides.length)%slides.length;slides.forEach(function(s,j){s.classList.toggle('ativo',j===cur);});dots.forEach(function(d,j){d.classList.toggle('ativo',j===cur);});}function restart(){clearInterval(timer);timer=setInterval(function(){show(cur+1);},3200);}prevBtn.addEventListener('click',function(){show(cur-1);restart();});nextBtn.addEventListener('click',function(){show(cur+1);restart();});slider.addEventListener('mouseenter',function(){clearInterval(timer);});slider.addEventListener('mouseleave',restart);show(cur);restart();}
            var initCursoId='{{ form_data.get("curso_id","") }}',initLocalId='{{ form_data.get("local_id","") }}',initOpcaoId='{{ form_data.get("opcao_id","") }}';
            if(initCursoId){courseSelect.value=initCursoId;atualizarLocaisPorCurso(initCursoId,initLocalId,initOpcaoId);}else{localGroup.style.display='none';turmaGroup.style.display='none';}
            if(initOpcaoId&&courseOptionsById[initOpcaoId])mostrarInfoCurso(true);
            benefitsSliders.forEach(initBenefitsSlider);
            syncReview();
            mostrarPasso(stepOrder.includes(startStep)?startStep:'index');
        });
    </script>
</body>
</html>
"""


TEMPLATE_CONFIRMACAO = r"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>MOVIMENTA RIO</title>
    <link rel="stylesheet" href="/static/style.css">
    <link rel="stylesheet" href="/static/assistant.css">
    <link href="https://fonts.googleapis.com/css2?family=Wise:wght@400;700;900&display=swap" rel="stylesheet">
    <script>
        !function(f,b,e,v,n,t,s)
        {if(f.fbq)return;n=f.fbq=function(){n.callMethod?
        n.callMethod.apply(n,arguments):n.queue.push(arguments)};
        if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
        n.queue=[];t=b.createElement(e);t.async=!0;
        t.src=v;s=b.getElementsByTagName(e)[0];
        s.parentNode.insertBefore(t,s)}(window, document,'script',
        'https://connect.facebook.net/en_US/fbevents.js');
        fbq('init', '2008632536670997');
        fbq('track', 'PageView');
    </script>
    <style>
        :root{--cor-principal:#2563eb;--cor-clara:#eff6ff;--cor-texto:#1e3a5f;--sombra-card:0 18px 55px rgba(37,99,235,0.18);}
        body{min-height:100vh;margin:0;background:radial-gradient(circle at top left,rgba(37,99,235,0.15),transparent 32%),linear-gradient(140deg,#eff6ff 0%,#fff 55%,#dbeafe 100%);font-family:'Wise',Arial,sans-serif;}
        .main-header{border-bottom:4px solid #2563eb;background:rgba(255,255,255,0.92);}.header-logos{display:flex;align-items:center;justify-content:center;padding:10px 20px;}.logo-prefeitura-topo{height:52px;width:auto;object-fit:contain;}
        .confirm-page{width:min(680px,calc(100% - 16px));margin:0 auto;padding:10px 0 20px;text-align:center;}
        .wizard-progress{margin:12px auto 16px;padding:14px 14px 16px;border-radius:28px;background:rgba(255,255,255,0.9);box-shadow:0 12px 30px rgba(37,99,235,0.12);}
        .wizard-track{width:100%;height:14px;border-radius:999px;background:#dbeafe;overflow:hidden;}
        .wizard-fill{width:100%;height:100%;background:linear-gradient(90deg,#2563eb 0%,#60a5fa 100%);border-radius:999px;}
        .wizard-labels{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:12px;}
        .wizard-label{padding:10px 8px;border:1px solid #93c5fd;border-radius:16px;background:#fff;color:#1d4ed8;font-size:0.84rem;font-weight:700;text-align:center;}
        .wizard-label.ativo{border-color:#2563eb;background:#eff6ff;color:#2563eb;}
        .confirm-shell{background:rgba(255,255,255,0.88);border:1px solid rgba(255,255,255,0.9);border-radius:30px;box-shadow:var(--sombra-card);overflow:hidden;text-align:center;}
        .confirm-card{padding:20px 16px 18px;max-width:620px;margin:0 auto;text-align:center;}
        .checkmark{width:120px;height:120px;margin:0 auto 12px;}
        .checkmark svg{width:100%;height:100%;stroke:#2563eb;fill:none;}
        .confirm-card h1{margin:0 0 10px;color:#2563eb;font-size:clamp(1.8rem,4vw,2.6rem);letter-spacing:-0.04em;}
        .protocol-box{margin:16px auto 12px;padding:14px;max-width:320px;border-radius:16px;background:#eff6ff;border:2px solid #2563eb;}
        .protocol-box strong{display:block;color:#2563eb;font-size:0.98rem;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.04em;}
        .protocol-box span{display:block;color:#2563eb;font-size:1.35rem;font-weight:900;letter-spacing:0.08em;word-break:break-all;}
        .next-steps{margin:16px auto 0;max-width:460px;padding:14px;border-radius:18px;background:#fff;border:1px solid #bfdbfe;}
        .next-steps h2{margin:0 0 12px;color:#2563eb;font-size:1.2rem;}
        .next-steps ol{margin:0;padding-left:22px;color:#1d4ed8;line-height:1.55;list-style-position:inside;}
        .actions{display:grid;gap:10px;margin-top:16px;max-width:380px;margin-left:auto;margin-right:auto;}
        .action-button{display:flex;align-items:center;justify-content:center;min-height:42px;padding:10px 14px;border-radius:12px;text-decoration:none;text-transform:uppercase;font-weight:800;letter-spacing:0.03em;transition:transform 0.16s ease;}
        .action-button.primary{background:linear-gradient(90deg,#2563eb 0%,#60a5fa 100%);color:#fff;box-shadow:0 10px 24px rgba(37,99,235,0.24);}
        .action-button.secondary{background:#fff;color:#2563eb;border:2px solid #2563eb;}
        .action-button:hover{transform:translateY(-1px);}
        @media(max-width:640px){html,body{width:100%!important;max-width:100%!important;overflow-x:hidden!important;}body*{min-width:0;}.main-header{padding:10px 12px;}.header-logos{display:flex;flex-direction:column;align-items:center;gap:10px;}.header-logos img{max-width:min(88vw,280px);height:auto;}.confirm-page{width:calc(100% - 8px)!important;max-width:100%!important;padding:6px 0 12px;}.confirm-card{width:100%!important;max-width:100%!important;padding:14px 10px 12px;}.wizard-progress{width:100%!important;max-width:100%!important;padding:10px;border-radius:18px;}.wizard-labels{grid-template-columns:1fr;gap:6px;}.confirm-shell{width:100%!important;max-width:100%!important;border-radius:18px;}.protocol-box span{font-size:1.3rem;}.next-steps,.actions,.action-button,.protocol-box,.wizard-label,.wizard-track{width:100%!important;max-width:100%!important;}img,svg{max-width:100%!important;height:auto!important;}}
    </style>
</head>
<body>
    <noscript><img height="1" width="1" style="display:none" src="https://www.facebook.com/tr?id=2008632536670997&ev=PageView&noscript=1"/></noscript>
    <script src="/static/assistant.js"></script>
    <header class="main-header">
        <div class="header-logos">
            <img src="/static/logo-prefeitura.png" alt="Prefeitura do Rio" class="logo-prefeitura-topo">
        </div>
    </header>
    <div class="confirm-page">
        <div class="wizard-progress">
            <div class="wizard-track"><div class="wizard-fill"></div></div>
            <div class="wizard-labels">
                <div class="wizard-label">1. In&#237;cio</div>
                <div class="wizard-label">2. Dados pessoais</div>
                <div class="wizard-label">3. Escolher</div>
                <div class="wizard-label ativo">4. Confirma&#231;&#227;o</div>
            </div>
        </div>
        <div class="confirm-shell"><div class="confirm-card">
            <div class="checkmark"><svg viewBox="0 0 200 200"><circle cx="100" cy="100" r="90" stroke-width="16"></circle><polyline points="60,110 95,145 145,75" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"></polyline></svg></div>
            <h1>Inscri&#231;&#227;o realizada com sucesso</h1>
            <div class="protocol-box"><strong>N&#250;mero de protocolo</strong><span>{{ protocolo }}</span></div>
            <div class="actions">
                <a class="action-button primary" href="{{ whatsapp_share_url }}" target="_blank" rel="noopener noreferrer">Compartilhar no WhatsApp</a>
                <a class="action-button secondary" href="{{ url_for('home') }}">Voltar ao in&#237;cio</a>
            </div>
            <div class="next-steps"><h2>Pr&#243;ximos passos</h2><ol>
                <li>Aguarde nosso contato via WhatsApp.</li>
                <li>Prepare RG, CPF e comprovante de resid&#234;ncia.</li>
                <li>Fique atento ao contato com os detalhes do curso.</li>
                <li>Compare&#231;a ao local informado no dia marcado.</li>
            </ol></div>
        </div></div>
    </div>
</body>
</html>
"""

# =============================================================================
# FLASK APP
# =============================================================================
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "chave-secreta-para-sessao")

def get_default_form_data(source=None):
    form_data = {
        "nome":"","genero":"","cpf":"","nascimento":"",
        "whatsapp":"","cep":"","bairro":"","email":"",
        "local_id":"","curso_id":"","opcao_id":"",
        "local":"","curso":"","turma":"",
        "dias_aula":"","horario":"","data_inicio":"",
        "encerramento":"","endereco_curso":"",
        "como_conheceu":"","confirma_dados":"",
    }
    if source:
        for key in form_data:
            value = source.get(key, form_data[key])
            if key == "confirma_dados":
                form_data[key] = "sim" if value else ""
            else:
                form_data[key] = (value or "").strip()
        fill_form_data_from_selection(form_data)
    return form_data

def cpf_valido(cpf):
    digits = re.sub(r"\D", "", cpf or "")
    if len(digits) != 11 or len(set(digits)) == 1: return False
    total = sum(int(digits[i]) * (10 - i) for i in range(9))
    digit = (total * 10) % 11; digit = 0 if digit == 10 else digit
    if digit != int(digits[9]): return False
    total = sum(int(digits[i]) * (11 - i) for i in range(10))
    digit = (total * 10) % 11; digit = 0 if digit == 10 else digit
    return digit == int(digits[10])

def idade_aceita(nascimento):
    try: dn = datetime.strptime(nascimento, "%d/%m/%Y")
    except ValueError: return False
    hoje = datetime.today(); idade = hoje.year - dn.year
    if (hoje.month, hoje.day) < (dn.month, dn.day): idade -= 1
    return 16 <= idade <= 90

def whatsapp_valido(whatsapp):
    digits = re.sub(r"\D", "", whatsapp or "")
    if len(digits) != 11: return False
    if not re.fullmatch(r"\(\d{2}\) \d{5}-\d{4}", whatsapp or ""): return False
    return digits[:2] in VALID_DDDS

def validate_form_data(form_data):
    errors = {}
    selected_curso  = form_data.get("curso_id")
    selected_option = get_course_option(form_data.get("opcao_id",""))
    if not selected_curso: errors["curso_id"] = "Selecione um curso."
    if not selected_option:
        errors["curso_id"] = errors.get("curso_id", "Selecione um local e hor\u00e1rio para o curso.")
    elif selected_option and selected_curso and selected_option["curso_id"] != selected_curso:
        errors["curso_id"] = "A turma n\u00e3o pertence ao curso escolhido."
    nome = form_data["nome"]
    if not nome: errors["nome"] = "Digite seu nome completo."
    elif len(nome) > 50: errors["nome"] = "O nome deve ter no m\u00e1ximo 50 caracteres."
    elif not NAME_PATTERN.fullmatch(nome): errors["nome"] = "Use apenas letras e sinais permitidos no nome."
    if form_data["genero"] not in {"Feminino","Masculino","Outro","Prefiro n\u00e3o dizer"}:
        errors["genero"] = "Selecione o g\u00eanero."
    if not cpf_valido(form_data["cpf"]): errors["cpf"] = "CPF inv\u00e1lido."
    if not idade_aceita(form_data["nascimento"]): errors["nascimento"] = "Idade permitida: de 16 at\u00e9 90 anos."
    if not whatsapp_valido(form_data["whatsapp"]): errors["whatsapp"] = "Informe um WhatsApp com DDD v\u00e1lido do Brasil."
    if not re.fullmatch(r"\d{5}-\d{3}", form_data["cep"] or ""): errors["cep"] = "CEP inv\u00e1lido. Formato: 00000-000."
    bairro = form_data["bairro"]
    if not bairro: errors["bairro"] = "Informe o bairro."
    elif len(bairro) > 40: errors["bairro"] = "O bairro deve ter no m\u00e1ximo 40 caracteres."
    if not ALLOWED_EMAIL_PATTERN.fullmatch(form_data["email"] or ""):
        errors["email"] = "Digite um e-mail v\u00e1lido do Gmail, Hotmail, Outlook ou Yahoo."
    if form_data["confirma_dados"] != "sim":
        errors["confirma_dados"] = "Confirme os dados para finalizar a inscri\u00e7\u00e3o."
    return errors

def error_step(errors):
    if "confirma_dados" in errors: return "revisao"
    if "curso_id" in errors: return "escolher"
    return "dados"

def render_wizard(form_data=None, errors=None, current_step="index"):
    current_form_data = form_data or get_default_form_data()
    selected_option = get_course_option(current_form_data.get("opcao_id")) or COURSE_INFO
    return render_template_string(
        TEMPLATE_WIZARD,
        course_info    = selected_option,
        local_options  = LOCAL_OPTIONS,
        course_catalog = COURSE_CATALOG,
        course_options = COURSE_OPTIONS,
        current_step   = current_step,
        errors         = errors or {},
        form_data      = current_form_data,
        generos        = ["Feminino","Masculino","Outro","Prefiro n\u00e3o dizer"],
    )

@app.route("/", methods=["GET"])
def home(): return render_wizard()

@app.route("/inscricao", methods=["GET","POST"])
def inscricao_unica():
    if request.method == "GET": return redirect(url_for("home"))
    form_data = get_default_form_data(request.form)
    errors    = validate_form_data(form_data)
    if errors: return render_wizard(form_data=form_data, errors=errors, current_step=error_step(errors))
    protocolo = str(uuid.uuid4())[:8].upper()
    session["protocolo"] = protocolo
    session.permanent = True
    dados = [
        protocolo, form_data["nome"], form_data["genero"], form_data["cpf"],
        form_data["nascimento"], form_data["whatsapp"], form_data["email"],
        form_data["cep"], form_data["bairro"], form_data["local"],
        form_data["curso"], form_data["turma"], form_data["dias_aula"],
        form_data["horario"], form_data["data_inicio"], form_data["encerramento"],
        form_data["endereco_curso"], form_data["como_conheceu"],
    ]
    try: append_to_sheet(dados)
    except Exception as exc: print("Erro ao salvar na planilha:", exc); traceback.print_exc()
    try:
        response = send_registration_to_supabase(form_data)
        print("Supabase:", response.status_code)
    except Exception as exc: print("Erro Supabase:", exc)
    return redirect(url_for("confirmacao", protocolo=protocolo))

@app.route("/curso",   methods=["GET","POST"])
@app.route("/revisao", methods=["GET","POST"])
@app.route("/wizard",  methods=["GET"])
def legacy_routes(): return redirect(url_for("home"))

@app.route("/confirmacao", methods=["GET"])
@app.route("/confirmacao/<protocolo>", methods=["GET"])
def confirmacao(protocolo=None):
    if not protocolo:
        protocolo = session.get("protocolo")
    if not protocolo: return redirect(url_for("home"))
    home_url = "https://movimenta-rio-mare.onrender.com"
    return render_template_string(
        TEMPLATE_CONFIRMACAO,
        protocolo          = protocolo,
        whatsapp_share_url = build_whatsapp_share_url(home_url),
    )

# =============================================================================
# SUPABASE
# =============================================================================
SUPABASE_FUNCTION_URL = os.environ.get(
    "SUPABASE_FUNCTION_URL",
    "https://egpyhfzatabyftwajoad.supabase.co/functions/v1/fgm-register",
)
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "jyUskwXkc54ZcMPyADLFN6LvZO0I60e3")

def normalize_phone_number(phone):
    digits = re.sub(r"[^\d]", "", phone or "")
    return f"55{digits}" if len(digits) == 11 else digits

def send_registration_to_supabase(form_data):
    phone   = normalize_phone_number(form_data.get("whatsapp",""))
    endereco = form_data.get("endereco_curso","").lstrip("\U0001f4cd\U0001f4cc ").strip()
    payload = {
        "name":           form_data.get("nome",""),
        "phone":          phone,
        "curso":          form_data.get("curso",""),
        "local":          form_data.get("local",""),
        "dia_semana":     form_data.get("dias_aula",""),
        "dias_semana":    form_data.get("dias_aula",""),
        "data_inicio":    form_data.get("data_inicio",""),
        "data_inscricao": datetime.utcnow().isoformat() + "Z",
        "horario":        form_data.get("horario",""),
        "endere\u00e7o": endereco,
        "endereco":       endereco,
        "turma":          form_data.get("turma",""),
    }
    headers = {
        "Content-Type":  "application/json",
        "Accept":        "application/json",
        "x-api-key":     SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
    }
    response = requests.post(SUPABASE_FUNCTION_URL, headers=headers, json=payload, timeout=10)
    if not response.ok:
        raise RuntimeError(f"Supabase retornou {response.status_code}: {response.text[:500]}")
    return response

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
