#!/usr/bin/env python3
import sys
import argparse
import logging
from src.bot import MonitorBot

# Configuração básica de logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger("Main")

def main():
    parser = argparse.ArgumentParser(description="Monitor LoTW Satélite Refatorado")
    parser.add_argument(
        "--mode", 
        choices=["check", "bot"], 
        default="check",
        help="Modo de execução: 'check' (uma vez) ou 'bot' (contínuo)"
    )
    args = parser.parse_args()

    try:
        # Instancia o bot (que carrega config e storage)
        bot = MonitorBot()
        
        if args.mode == "check":
            logger.info("Executando ciclo único de verificação...")
            # Roda síncrono
            bot.run_check_job(manual=False)
            logger.info("Ciclo concluído.")
            
        elif args.mode == "bot":
            logger.info("Iniciando modo Bot Interativo...")
            bot.start_polling()
            
    except ValueError as ve:
        logger.critical(f"Erro de configuração: {ve}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Interrompido pelo usuário.")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Erro inesperado: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
