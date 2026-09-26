# Colab

Upload `semanticdrift_colab.ipynb` to Google Colab (Runtime → GPU).

After you push this repo, set `REPO_URL` in the clone cell. For a **private** repo, add a read-only GitHub token as a Colab secret named `GITHUB_TOKEN` (the key icon). Do not put `.github_token` from the laptop into the notebook or the zip.

First cells install SPIN and prove gold Promela. Ollama / Qwen is optional and last.
