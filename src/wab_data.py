import re

# Grid to State Mapping for Brazil
# Source: Derived from major cities/capitals and common knowledge
GRID_TO_STATE = {
    # AC - Rio Branco
    "FI60": "AC", "FI61": "AC",
    # AL - Maceió
    "HH20": "AL",
    # AP - Macapá
    "GI90": "AP", "GJ90": "AP",
    # AM - Manaus
    "FI66": "AM", "FJ92": "AM", "GJ93": "AM",
    # BA - Salvador
    "HH17": "BA", "HH27": "BA", "HH38": "BA", "GH56": "BA",
    # CE - Fortaleza
    "HK16": "CE", "HI16": "CE", "HI06": "CE",
    # DF - Brasília
    "GH64": "DF",
    # ES - Vitória
    "GG99": "ES", "GH90": "ES",
    # GO - Goiânia (GH63)
    "GH63": "GO", "GH53": "GO",
    # MA - São Luís
    "GI87": "MA", "GI75": "MA",
    # MT - Cuiabá
    "GH34": "MT", "GH44": "MT",
    # MS - Campo Grande
    "GH49": "MS", "GH59": "MS",
    # MG - BH
    "GH70": "MG", "GH80": "MG", "GH81": "MG", "GH71": "MG", "GG79": "MG",
    # PA - Belém
    "GI98": "PA", "GI88": "PA", "GI89": "PA",
    # PB - João Pessoa
    "HI22": "PB", "HI23": "PB",
    # PR - Curitiba
    "GG54": "PR", "GG44": "PR", "GG64": "PR",
    # PE - Recife
    "HI21": "PE", "HI11": "PE", "HI31": "PE",
    # PI - Teresina
    "GI84": "PI", "GI74": "PI",
    # RJ - Rio
    "GG87": "RJ", "GG77": "RJ", "GG88": "RJ",
    # RN - Natal
    "HI24": "RN", "HI34": "RN",
    # RS - Porto Alegre
    "GG49": "RS", "GG39": "RS", "GG59": "RS", "GF49": "RS",
    # RO - Porto Velho
    "FI91": "RO", "FJ91": "RO",
    # RR - Boa Vista
    "FJ92": "RR",
    # SC - Florianópolis
    "GG52": "SC", "GG43": "SC",
    # SP - São Paulo
    "GG66": "SP", "GG67": "SP", "GG56": "SP", "GG76": "SP",
    # SE - Aracaju
    "HH19": "SE",
    # TO - Palmas
    "GH69": "TO", "GI60": "TO",
}

def get_state_from_grid(grid: str) -> str:
    """Mapeia Grid -> Estado (Prioridade sobre Callsign)."""
    if not grid or len(grid) < 4: return None
    grid = grid.upper().strip()[:4]
    return GRID_TO_STATE.get(grid)

def get_state_from_call(call: str) -> str:
    """
    Deduz o estado (UF) brasileiro baseado no indicativo (Callsign).
    Referência: ANATEL / LABRE / ITU.
    Retorna a sigla do estado (Ex: 'SP', 'RJ') ou None se não encontrado.
    """
    call = call.upper().strip()
    
    # Regex para separar Prefixo, Número e Sufixo
    # Ex: PU7SDE -> Pfx: PU, Reg: 7, Suf: SDE
    # Ex: PY2XYZ -> Pfx: PY, Reg: 2, Suf: XYZ
    # Ex: KD8XYZ (USA) -> None
    
    # 1. Verifica se é Brasil (PPA-PYZ, ZVA-ZZZ)
    if not re.match(r'^(PP|PQ|PR|PS|PT|PU|PV|PW|PX|PY|ZV|ZW|ZX|ZY|ZZ)', call):
        return None

    # Parse mais detalhado
    match = re.match(r'^([A-Z]{2})([0-9])([A-Z]+)', call)
    if not match:
        return None
        
    pfx, reg, suf = match.groups()
    reg = int(reg)
    
    # --- LOGICA DE REGIOES ---
    
    # REGIÃO 1: RJ, ES
    if reg == 1:
        if pfx == 'PP': return 'ES'
        if pfx == 'PY': return 'RJ'
        if pfx == 'PU':
            if 'AAA' <= suf <= 'IZZ': return 'ES'
            return 'RJ'
        return 'RJ'

    # REGIÃO 2: SP, GO, DF, TO
    if reg == 2:
        if pfx == 'PQ': return 'TO'
        if pfx == 'PT': return 'DF'
        if pfx == 'PP': return 'GO'
        if pfx == 'PY': return 'SP'
        if pfx == 'PU':
            if 'AAA' <= suf <= 'EZZ': return 'DF'
            if 'FAA' <= suf <= 'HZZ': return 'GO'
            return 'SP' # Default (Maioria PU2 é SP)
        return 'SP'

    # REGIÃO 3: RS
    if reg == 3:
        return 'RS'

    # REGIÃO 4: MG
    if reg == 4:
        return 'MG'

    # REGIÃO 5: SC, PR
    if reg == 5:
        if pfx == 'PP': return 'SC'
        if pfx == 'PY': return 'PR'
        if pfx == 'PU':
             if 'AAA' <= suf <= 'LZZ': return 'SC'
             return 'PR'
        return 'PR'

    # REGIÃO 6: BA, SE
    if reg == 6:
        if pfx == 'PP': return 'SE'
        if pfx == 'PY': return 'BA'
        if pfx == 'PU':
            if 'AAA' <= suf <= 'IZZ': return 'SE'
            return 'BA'
        return 'BA'

    # REGIÃO 7: AL, CE, PB, PE, PI, RN
    if reg == 7:
        if pfx == 'PP': return 'AL'
        if pfx == 'PT': return 'CE'
        if pfx == 'PR': return 'PB'
        if pfx == 'PY': return 'PE'
        if pfx == 'PS': return 'RN'
        if pfx == 'PU':
            if suf.startswith(('A','B','C','D')): return 'AL'
            if suf.startswith(('E','F','G','H')): return 'PB'
            if suf.startswith(('M','N','O','P')): return 'CE'
            if suf.startswith('R'): return 'PE'
            if suf.startswith('S'): return 'RN'
        return 'PE'

    # REGIÃO 8: AC, AP, AM, MA, PA, PI, RO, RR
    if reg == 8:
        if pfx == 'PT': return 'AC'
        if pfx == 'PQ': return 'AP'
        if pfx == 'PP': return 'AM'
        if pfx == 'PR': return 'MA' # MA is listed as PR8 in some sources, others PS8? Wait, PS8=PI. Let's trust PR=MA.
        if pfx == 'PY': return 'PA'
        if pfx == 'PS': return 'PI' # PI (Piauí) uses PS8
        if pfx == 'PW': return 'RO'
        if pfx == 'PV': return 'RR'
        if pfx == 'PU':
             if 'AAA' <= suf <= 'CZZ': return 'AM'
             if 'DAA' <= suf <= 'FZZ': return 'RR'
             if 'GAA' <= suf <= 'IZZ': return 'AP'
             if 'JAA' <= suf <= 'LZZ': return 'AC'
             if 'MAA' <= suf <= 'OZZ': return 'MA'
             if 'PAA' <= suf <= 'SZZ': return 'PI'
             if 'TAA' <= suf <= 'VZZ': return 'RO'
             if 'WAA' <= suf <= 'YZZ': return 'PA'
        return 'AM'

    # REGIÃO 9: MT, MS
    if reg == 9:
        if pfx == 'PY': return 'MT'
        if pfx == 'PT': return 'MS'
        if pfx == 'PU':
            if 'AAA' <= suf <= 'NZZ': return 'MS'
            if 'OAA' <= suf <= 'YZZ': return 'MT'
        return 'MT'
        
    # Region 0 (Islands)
    if reg == 0:
        if suf.startswith('F'): return 'PE'
        if suf.startswith('T'): return 'ES'
        return 'PE'

    return None

def get_all_states():
    return [
       'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 
       'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 
       'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'
    ]
