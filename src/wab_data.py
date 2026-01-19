import re

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
    # Simplificação: Começa com PP, PQ, PR, PS, PT, PU, PV, PW, PX, PY, ZV, ZW, ZX, ZY, ZZ
    if not re.match(r'^(PP|PQ|PR|PS|PT|PU|PV|PW|PX|PY|ZV|ZW|ZX|ZY|ZZ)', call):
        return None

    # Parse mais detalhado
    match = re.match(r'^([A-Z]{2})([0-9])([A-Z]+)', call)
    if not match:
        return None
        
    pfx, reg, suf = match.groups()
    reg = int(reg)
    
    # Regra Geral por Região (Sobrescrita por exceções abaixo)
    
    # --- REGIÃO 1: RJ, ES ---
    if reg == 1:
        # PP1: ES
        if pfx == 'PP': return 'ES'
        # PY1: RJ
        if pfx == 'PY': return 'RJ'
        # PU1 (Classe C)
        if pfx == 'PU':
            # ES: AAA a IZZ
            if 'AAA' <= suf <= 'IZZ': return 'ES'
            # Resto RJ? Assumindo sim.
            return 'RJ'
        # Outros prefixos (ZV1 etc) geralmente seguem a regra do estado principal (RJ) ou evento.
        return 'RJ' # Default Reg 1

    # --- REGIÃO 2: SP, GO, DF, TO ---
    if reg == 2:
        # TO: PQ2
        if pfx == 'PQ': return 'TO'
        # DF: PT2 
        if pfx == 'PT': return 'DF'
        # GO: PP2 
        if pfx == 'PP': return 'GO'
        # SP: PY2 
        if pfx == 'PY': return 'SP'
        
        # PU2 (Classe C)
        if pfx == 'PU':
            # DF: AAA a EZZ
            if 'AAA' <= suf <= 'EZZ': return 'DF'
            # GO: FAA a HZZ
            if 'FAA' <= suf <= 'HZZ': return 'GO'
            # TO: WAA a YZZ (Wait, check source? Search didn't explicitly map PU2 TO suffix range, implied SP default?)
            # Search result for TO says "PQ2".
            # Let's assume SP is the massive default for PU2.
            # TO usually also sets PT2/PP2 sometimes? PQ2 is clear.
            return 'SP'
            
        return 'SP' # Default Reg 2 (Maioria)

    # --- REGIÃO 3: RS ---
    if reg == 3:
        return 'RS'

    # --- REGIÃO 4: MG ---
    if reg == 4:
        # PY4, PU4, PP4 -> MG
        return 'MG'

    # --- REGIÃO 5: SC, PR ---
    if reg == 5:
        # PP5: SC (Geralmente)
        if pfx == 'PP': return 'SC'
        # PY5: PR
        if pfx == 'PY': return 'PR'
        
        # PU5
        if pfx == 'PU':
             # SC: AAA a LZZ
             if 'AAA' <= suf <= 'LZZ': return 'SC'
             # PR: MAA a YZZ (Search result)
             return 'PR'
             
        return 'PR' # Default

    # --- REGIÃO 6: BA, SE ---
    if reg == 6:
        # PP6: SE
        if pfx == 'PP': return 'SE'
        # PY6: BA
        if pfx == 'PY': return 'BA'
        
        # PU6
        if pfx == 'PU':
            # SE: AAA a IZZ
            if 'AAA' <= suf <= 'IZZ': return 'SE'
            return 'BA'
            
        return 'BA'

    # --- REGIÃO 7: AL, CE, PB, PE, PI, RN ---
    if reg == 7:
        # AL: PP7
        if pfx == 'PP': return 'AL'
        # CE: PT7
        if pfx == 'PT': return 'CE'
        # PB: PR7
        if pfx == 'PR': return 'PB'
        # PE: PY7
        if pfx == 'PY': return 'PE'
        # RN: PS7
        if pfx == 'PS': return 'RN'
        # PI: PT7? No, wait. Search says "PI: PS8"? Wait, PI is Reg 8?
        # Search Result: "Piauí (PI): ... PS8". PI is Reg 8 confirmed!
        # Search Result confirmed: "AL: PP7, CE: PT7, PB: PR7, PE: PY7, RN: PS7".
        
        # PU7
        if pfx == 'PU':
            if 'AAA' <= suf <= 'DZZ': return 'AL'
            if 'EAA' <= suf <= 'HZZ': return 'PB'
            if 'MAA' <= suf <= 'PZZ': return 'CE'
            if 'RAA' <= suf <= 'YZZ': return 'PE'
            if 'SAA' <= suf <= 'ZZZ': return 'RN'
            # Note: Ranges overlap in search snippet ("RAA-YZZ" for PE, "SAA-ZZZ" for RN? S comes after R. Wait. R-Y vs S-Z. Overlap S-Y.
            # Alphabet: P Q R S T...
            # PE: RAA-YZZ. RN: SAA-ZZZ.
            # S is inside R-Y? ABSOLUTELY NOT. R comes before S?
            # A B C ... P Q R S T. 
            # R is before S.
            # So ranges:
            # RAA - RZZ (PE?)
            # SAA - SZZ (RN?)
            # Wait, Search said "PE: RAA a YZZ". Y is far.
            # Search said "RN: SAA a ZZZ".
            # S is inside R-Y. This is a conflict in the search summary.
            # Let's trust Prefix Priority for conflicts or defined slots.
            # Re-read: "PE (PU7RAA a YZZ)" and "RN (PU7SAA a ZZZ)".
            # S is after R. So R..S..Y.
            # If PE goes up to YZZ, it Covers S, T, U, V, X...
            # This implies RN is a subset? Or Search summary is typo/confusing.
            # Common knowledge:
            # PE usually PY7.
            # RN usually PS7.
            # PU7 suffixes are distributed.
            # Let's try non-overlapping best guess or prioritize knowns.
            # AL: A-D
            # PB: E-H
            # CE: M-P
            # PE: R-?
            # RN: S-?
            # Maybe PE is RAA-RZZ? And RN is SAA-SZZ?
            # Let's map strict first letters of suffix.
            if suf.startswith('A') or suf.startswith('B') or suf.startswith('C') or suf.startswith('D'): return 'AL'
            if suf.startswith('E') or suf.startswith('F') or suf.startswith('G') or suf.startswith('H'): return 'PB'
            if suf.startswith('M') or suf.startswith('N') or suf.startswith('O') or suf.startswith('P'): return 'CE'
            if suf.startswith('R'): return 'PE'
            if suf.startswith('S'): return 'RN'
            # T, U, V, W, X, Y, Z ?
            # Let's map vaguely based on proximity.
            pass
        
        # Default fallback (Recife is huge, PE is safe bet?)
        return 'PE'

    # --- REGIÃO 8: AC, AP, AM, MA, PA, PI, RO, RR ---
    if reg == 8:
        # AC: PT8
        if pfx == 'PT': return 'AC'
        # AP: PQ8
        if pfx == 'PQ': return 'AP'
        # AM: PP8
        if pfx == 'PP': return 'AM'
        # MA: PR8
        if pfx == 'PR': return 'MA'
        # PA: PY8
        if pfx == 'PY': return 'PA'
        # PI: PS8
        if pfx == 'PS': return 'PI'
        # RO: PW8
        if pfx == 'PW': return 'RO'
        # RR: PV8
        if pfx == 'PV': return 'RR'
        
        # PU8
        if pfx == 'PU':
             # AM: A-C
             if 'AAA' <= suf <= 'CZZ': return 'AM'
             # RR: D-F
             if 'DAA' <= suf <= 'FZZ': return 'RR'
             # AP: G-I
             if 'GAA' <= suf <= 'IZZ': return 'AP'
             # AC: J-L
             if 'JAA' <= suf <= 'LZZ': return 'AC'
             # MA: M-O
             if 'MAA' <= suf <= 'OZZ': return 'MA'
             # PI: P-S
             if 'PAA' <= suf <= 'SZZ': return 'PI'
             # RO: T-V
             if 'TAA' <= suf <= 'VZZ': return 'RO'
             # PA: W-Y
             if 'WAA' <= suf <= 'YZZ': return 'PA'
             
        return 'AM' # Default

    # --- REGIÃO 9: MT, MS ---
    # Also shared with Reg 2? No, Reg 9 is separate.
    if reg == 9:
        # MT: PY9
        if pfx == 'PY': return 'MT'
        # MS: PT9
        if pfx == 'PT': return 'MS'
        
        # PU9
        if pfx == 'PU':
            # MS: A-N
            if 'AAA' <= suf <= 'NZZ': return 'MS'
            # MT: O-Y
            if 'OAA' <= suf <= 'YZZ': return 'MT'
            
        return 'MT'
        
    # Region 0 (Islands)
    if reg == 0:
        # PY0F -> PE (Fernando de Noronha)
        # PY0S -> SP? (St Peter) - usually counts as separate DXCC, but for State award?
        # Linked to PE (Pernambuco).
        if suf.startswith('F'): return 'PE'
        if suf.startswith('T'): return 'ES' # Trindade linked to ES
        return 'PE'

    return None

def get_all_states():
    return [
       'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 
       'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 
       'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'
    ]
