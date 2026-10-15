---
name: agent-board
description: À charger quand tu lances ou gères des sous-agents et que l'agent board est installé (~/.local/opt/agent-board), pour les afficher sur le tableau (load when you launch or manage sub-agents and the agent board is installed).
---

# Agent board

Une page en direct (http://127.0.0.1:8120) qui montre les sous-agents : titre, nom, statut, actions, exécutions de tests, vue du navigateur.

## Est-il démarré ?

`curl -s 127.0.0.1:8120/api/state`. Si ça échoue et que le board n'est pas installé (pas de `~/.local/opt/agent-board`), lance `~/.local/opt/agent-board/install.sh` (clone-le d'abord, voir AGENTS.md). Sinon démarre-le :
`(setsid nohup python3 ~/.local/opt/agent-board/board.py serve > /dev/null 2>&1 &)`

## Inscrire un sous-agent

L'id de l'agent est `agent-<id>`, le nom de base de son worktree (ce qu'utilisent le hook et les lanceurs de tests). Juste après avoir lancé un sous-agent dans un worktree :

```bash
B=~/.local/opt/agent-board/board.py
python3 $B archive --except agent-<id>     # archives the project's other agents (only this project's)
python3 $B agent agent-<id> --title "..." --name "..." --status working --branch <branch> \
  --checkout <main checkout>/.claude/worktrees/agent-<id>
```

Puis mets son statut à jour :

- à la relecture : `python3 $B agent agent-<id> --status review --pr <url>`
- après le merge : `python3 $B agent agent-<id> --status done`

## Usage (limites du forfait, fenêtre de contexte)

**Le bandeau (5 h, hebdo, contexte) ne se met pas à jour tout seul : c'est à toi de le rafraîchir, régulièrement.** Dans l'app de bureau Claude, appelle l'outil `get_usage` de l'app, écris sa sortie JSON telle quelle dans un fichier de ton dossier temporaire (ou passe-la sur l'entrée standard), puis `python3 $B usage --file <ce fichier>`.

Fais-le **à la fin de chaque tâche**, c'est-à-dire chaque fois que tu rends la main à l'utilisateur, et aussi à chaque étape de la boucle : début de session, lancement d'un sous-agent, relecture, merge. Un bandeau périmé est un bug : l'utilisateur s'en sert pour suivre ses limites. Préviens l'utilisateur quand une limite approche de 80 %.

## État du pilote

Le pilote tient sa ligne à jour (depuis le checkout du projet) : `python3 $B pilot --status busy` quand il travaille, `--status waiting --waiting "<ce qu'il attend, en une ligne>"` dès qu'il attend l'utilisateur (un accord de merge, une décision), `--status idle` quand il n'a plus rien en cours. **Dès qu'il reprend après une attente** (l'utilisateur répond, un sous-agent rend son rapport), sa première action est `--status busy`, avant tout le reste ; et il repasse en `waiting` juste avant de rendre la main. Sa fenêtre de contexte s'y affiche avec le relevé `usage`.

`board.py` sort avec le code 0, sans rien dire, quand le board est arrêté. Les actions viennent du hook global `PostToolUse` ; les lanceurs de tests rendent compte par l'API HTTP et `board_stream.py` (voir le README, « Plug in a test runner » et « Plug in a browser screencast »).
