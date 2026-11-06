# Open Vitæ pour Mac — 0.3.1

Application AppKit + WKWebView pour macOS 14+, Apple Silicon. Python, le service local, Codex et le navigateur de lecture des formulaires sont embarqués. Aucun terminal pour l’utilisateur. Le service écoute seulement sur 127.0.0.1 sur un port libre et s’arrête avec l’app.

## Installer et démarrer

Décompresser Open-vitae-Mac.zip, déplacer Open Vitae.app dans Applications, puis l’ouvrir. La compilation locale est signée ad hoc, sans notarisation Apple. Une diffusion publique nécessite signature Developer ID et notarisation ; ne pas désactiver Gatekeeper.

Un espace neuf est créé dans ~/Library/Application Support/Candidatures. Un ancien espace sélectionné est conservé ; le menu Fichier permet d’en changer. Les données restent hors du paquet. Se connecter à un fournisseur est obligatoire, puis le profil et l’import du CV permettent de commencer la recherche. Les dossiers existants restent conservés.

ChatGPT utilise Codex app-server et son parcours de connexion officiel, avec une session isolée et des identifiants gérés dans le trousseau macOS. Claude et Gemini utilisent leurs API : ce ne sont pas des connexions à leurs abonnements grand public. Les clés restent dans le trousseau. Les conditions et limites du fournisseur s’appliquent ; les frais ne sont pas inclus dans l’application gratuite.

La recherche publique et le classement local ne consomment pas de modèle. Le chat peut proposer des critères à confirmer et déclencher une recherche. Accepter une offre lance la préparation d’un brouillon de CV et de réponses ; relire le dossier, vérifier le formulaire et l’éligibilité, puis envoyer sur le site de l’entreprise. L’app ne soumet pas les candidatures automatiquement.

## Reconstruire

Python 3.11+, Swift/Xcode Command Line Tools et CLI Codex natif officiel requis. Avec une installation npm, `CODEX_BINARY` doit désigner le binaire macOS sous `vendor/aarch64-apple-darwin/codex/codex`, pas le lanceur JavaScript. Depuis la racine :

```sh
python3 -m venv --system-site-packages /tmp/candidatures-mac-build
/tmp/candidatures-mac-build/bin/python -m pip install -e '.[test]' 'pyinstaller>=6,<7'
PLAYWRIGHT_BROWSERS_PATH=/tmp/candidatures-browsers /tmp/candidatures-mac-build/bin/python -m playwright install chromium --only-shell
/tmp/candidatures-mac-build/bin/python macos/build.py
```

La compilation est générique, sans chemin personnel ni données de candidature. Aucun espace utilisateur n’est copié dans le paquet. Les licences embarquées sont dans Contents/Resources/licenses.

## Vérification

Les tests Python et navigateur utilisent des fournisseurs fictifs et un espace temporaire. Ils couvrent connexion obligatoire, onboarding, import, recherche, choix d’offres, préparation du PDF, consentements explicites et suivi manuel. La génération réelle dépend d’une connexion du propriétaire du compte et doit être vérifiée avec lui. Voir README pour les limites de sources, budgets, modèles et distribution.

Le nom affiché est Open Vitæ. L’identifiant du paquet, le trousseau, les préférences et le dossier Application Support/Candidatures restent stables pour préserver les espaces existants.

## Candidats de distribution

La version vient de `pyproject.toml`, le numéro de compilation de `macos/release.json`. Le script `build.py --release` exige Developer ID, la distribution Sparkle vérifiée, une clé publique Ed25519 et un flux HTTPS. `distribute.py` notarise et agrafe les tickets, puis crée le DMG avec un raccourci Applications. Le workflow manuel produit une release GitHub en brouillon. Voir les secrets, le flux de mise à jour, la vérification sur Mac propre et la récupération dans [RELEASING.md](../docs/RELEASING.md). Aucune réussite de notarisation ou de mise à jour réelle n’est revendiquée ici.
