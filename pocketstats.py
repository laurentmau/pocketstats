import pocket
from pocket import Pocket
import datetime
import click
import __main__ as main
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
Base = declarative_base()

def safe_unicode(obj, *args):
    """ return the unicode representation of obj """
    try:
        return unicode(obj, *args)
    except UnicodeDecodeError:
        # obj is byte string
        ascii_text = str(obj).encode('string_escape')
        return unicode(ascii_text)

def safe_str(obj):
    """ return the byte string representation of obj """
    try:
        return str(obj)
    except UnicodeEncodeError:
        # obj is unicode
        return unicode(obj).encode('unicode_escape')


def unix_to_string(timestamp):
    return datetime.datetime.fromtimestamp(int(timestamp)).strftime('%Y-%m-%d %H:%M:%S')


class Article(Base):
    __tablename__ = 'article'

    id = Column(Integer, primary_key=True)
    sort_id = Column(Integer)
    item_id = Column(Integer)
    resolved_id = Column(Integer)
    given_url = Column(String)
    resolved_url = Column(String)
    given_title = Column(String)
    resolved_title = Column(String)

    # 0 or 1 - 1 If the item is favorited
    favorite = Column(Integer)

    # 0, 1, 2 - 1 if the item is archived - 2 if the item should be deleted
    status = Column(Integer)

    excerpt = Column(Text)

    # 0 or 1 - 1 if the item is an article
    is_article = Column(Integer)

    # 0, 1, or 2 - 1 if the item has images in it - 2 if the item is an image
    has_image = Column(Integer)

    # 0, 1, or 2 - 1 if the item has videos in it - 2 if the item is a video
    has_video = Column(Integer)

    # How many words are in the article
    word_count = Column(Integer)

    # JSON objects
    tags = Column(Text)
    authors = Column(Text)
    images = Column(Text)
    videos = Column(Text)

    time_updated = Column(DateTime)
    time_favorited = Column(DateTime)
    time_read = Column(DateTime)


class Report(Base):
    """
    Changes since the last report; e.g., how many added, read, deleted, favourited
    """
    __tablename__ = 'report'

    id = Column(Integer, primary_key=True)


def get_pocket_instance():
    """
    Connect to Pocket API
    """
    try:
        import settings
    except ImportError:
        print('Copy settings_example.py to settings.py and set the configuration to your own preferences')
        sys.exit(1)

    consumer_key = settings.consumer_key
    access_token = settings.access_token

    pocket_instance = pocket.Pocket(consumer_key, access_token)
    return pocket_instance


def get_db_connection():
    """
    Create a SQLAlchemy session
    """
    engine = create_engine('sqlite:///:memory:', echo=True)
    Session = sessionmaker(bind=engine)
    return Session()


## Main program
@click.group()
def cli():
    """
    Pocket stats
    """
    pass


@cli.command()
def updatestats():
    """
    Get the changes since last time from the Pocket API
    """
    session = get_db_connection()

    #items = pocket_instance.get(state='unread')
    #print 'Number of items: ' + str(len(items[0]['list']))
    #items = pocket_instance.get(state='archive')
    #print 'Number of items: ' + str(len(items[0]['list']))
    #sys.exit()

    #items = pocket_instance.get()
    pocket_instance = get_pocket_instance()
    items = pocket_instance.get(count=10)
    #print items[0]['status']
    print 'Number of items: ' + str(len(items[0]['list']))

    for item_id in items[0]['list']:
        #print item_id
        item = items[0]['list'][item_id]
        print item
        #print safe_unicode(item['status']) + ' '+ safe_unicode(item['item_id']) + ' ' + safe_unicode(item['resolved_id']) + ' ' + safe_unicode(item['given_title'])
        print safe_unicode(item['status']) + ' ' + safe_unicode(item['item_id']) + ' ' + safe_unicode(item['resolved_id']) + ' ' + unix_to_string(item['time_added']) + ' ' + unix_to_string(item['time_updated'])
        #datetime.datetime.fromtimestamp(int(item['time_updated'])).strftime('%Y-%m-%d %H:%M:%S')
        #print safe_unicode(item['given_title'])
        print safe_unicode(item['resolved_url'])
        #print safe_unicode(item['resolved_title'])
        article = Article(sort_id=item['sort_id'], item_id=item['item_id'])
        article.resolved_id = item['resolved_id']
        session.add(article)

    session.commit()

    #items = pocket_instance.get(state='unread')
    #print items[0]['status']
    #print len(items[0]['list'])


@cli.command()
def gettoken():
    """
    Get access token
    """
    logger = get_logger()
    if settings.notification_type == 'pb':
        p, sendto_device = get_pushbullet_config(logger)
        if not sendto_device:
            sys.exit(1)

        local_version = get_local_version()
        p.push_note('ns-notifier test', 'Test message from ns-notifier ' + local_version + '. Godspeed!', sendto_device)

if not hasattr(main, '__file__'):
    """
    Running in interactive mode in the Python shell
    """
    print("Pocket stats running interactively in Python shell")

elif __name__ == '__main__':
    """
    Pocket stats is ran standalone, rock and roll
    """
    cli()
