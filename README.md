# pocketstats

Statistics of your [Pocket](https://getpocket.com) usage: how many are still unread, how many have you favourited, are deleted and are archived?

[![Code Health](https://landscape.io/github/aquatix/pocketstats/master/landscape.svg?style=flat)](https://landscape.io/github/aquatix/pocketstats/master)


`pocketstats` keeps track of the metadata of your saved items through the [Pocket API](https://getpocket.com/developer/) and is intended to be run periodically through cron (for example, once per day).

## Usage

First, [obtain an App token from the Pocket dev website](https://getpocket.com/developer/apps/new) (it only needs Read permissions, and can be of type 'Web').

Copy settings_example.py to settings.py and put the corresponding Consumer Key that the website lists, in settings.py under `consumer_key`. Now run pocketstats with the `gettoken` option, providing your Consumer Key on the command line (it will ask for it if you don't use the `--consumer_key` option):

```
python pocketstats.py gettoken --consumer_key=<consumer key>
```
