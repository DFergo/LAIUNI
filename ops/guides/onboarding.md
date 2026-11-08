# Onboarding survey

Ask before recommending anything. A few questions at a time, in the user's language, plain words. Skip what `check_machine` already tells you. Save the answers with `profile_save`.

## 1. About them
- Have you used a terminal / command line before? (never · a little · regularly)
- Have you run a server or Docker before? (no · a little · yes)
- Is there someone technical who can help (IT person, volunteer)?
→ Sets how much you explain. For "never", explain each step in one or two sentences, avoid jargon, and confirm what they see on screen.

## 2. What they want
- Who will use it: workers (anonymous reporting), union representatives, organisers / officers (internal), or several?
- How many frontends (sites) to start with, and in which languages?
- Should it be reachable from the Internet, or only inside the office network?
- Roughly how many users at the same time (a few, dozens, more)?

## 2b. Their organization
- Name of the organization and a short name; what the tool should be called (the default is "HRDD Helper").
- Brand colours (or the website to read them from) and their logo files. → guide `branding`, which also covers the prompt review when the organization is not UNI.

## 3. Machines
- Run `check_machine` on this computer (explain what it checks).
- Is this the machine that will run the backend? Will it stay on all the time? (A laptop that sleeps is fine to try, not for production.)
- Other machines available: another computer in the office? A VPS already? (provider, OS)
- For local AI models: does any machine have 32 GB of memory or more (Mac with Apple Silicon, or a PC with a strong NVIDIA GPU)?

## 4. Network and accounts
- Do they have a domain? (Usually yes, for the union website and email.) → explain in guide `domain-cloudflare` why the app should get **its own new domain**.
- Cloudflare account? Tailscale account? (Fine if not: we create them when needed.)

## 5. AI models
- Budget per month for AI (none · small · flexible)?
- Privacy requirements: conversations with workers are sensitive. Is sending them to a cloud AI provider acceptable? Only EU providers? Must everything stay in-house?
→ guides `inference` and `models`.

## 6. Email
- What email does the union use: Google Workspace / Gmail, Microsoft 365, its own mail server, other? Can they create a dedicated mailbox (e.g. `hrdd@union.org`)? → guide `email`.

## Then
Summarise what you understood and recommend a topology (guide `topologies`), with the reason, in a few lines. Let them choose.
