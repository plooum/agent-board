# AGENTS.md : utiliser agent-board dans un projet

Pour un agent IA à qui on dit d'utiliser ce tableau pour suivre ses sous-agents. Fais ceci dans l'ordre.

1. **Installer et lancer.** Vérifie : `curl -s 127.0.0.1:8120/api/state`. Si ça échoue :
   `git clone https://github.com/plooum/agent-board ~/.local/opt/agent-board && ~/.local/opt/agent-board/install.sh`
   **Préviens d'abord l'utilisateur** si `~/.claude/settings.json` existe déjà : le script ajoute un hook à cette configuration globale (il garde tout le reste et écrit un `.bak`). Une nouvelle session Claude Code peut être nécessaire pour que le hook s'applique. Le script est idempotent ; `--no-start` évite de démarrer le serveur.
2. **Pendant le pilotage.** Charge le skill `agent-board`. Lance les sous-agents avec l'isolation en worktree (le hook ne suit que les agents dans `.claude/worktrees/`). Inscris-les, archive-les et mets leur statut à jour comme le dit le skill.
3. **Brancher les tests du projet (facultatif).** Les lanceurs de tests postent des événements : README, « Plug in a test runner ». Les lanceurs Playwright diffusent le navigateur avec `board_stream.py` : README, « Plug in a browser screencast ». Le projet doit fonctionner sans le tableau : import dans un `try`, localisation par `AGENT_BOARD_HOME`, jamais d'échec quand le tableau est arrêté.
4. **Prévenir les agents suivants.** Ajoute une ligne au `CLAUDE.md` du projet (ou aux notes du pilote) : « Les sous-agents sont suivis sur l'agent board (https://github.com/plooum/agent-board) ; charge le skill `agent-board` avant de les lancer. »
5. **L'utilisateur regarde** sur http://127.0.0.1:8120 dans son propre navigateur (filtre par projet dans l'en-tête).
