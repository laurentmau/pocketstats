import datetime
import logging
import __main__ as main
import pocket
from pocket import Pocket
import click
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine.reflection import Inspector
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


def get_logger():
    """
    Create logging handler
    """
    ## Create logger
    logger = logging.getLogger('pocketstats')
    logger.setLevel(logging.DEBUG)
    # create file handler which logs even debug messages
    fh = logging.FileHandler('pocketstats.log')
    fh.setLevel(logging.DEBUG)
    # create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    # add the handlers to the logger
    logger.addHandler(fh)
    return logger


class Article(Base):
    """
    An item in the Pocket archive; can also be an Image or Video
    """
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
    # Local DateTime of request
    time_updated = Column(DateTime)
    # DateTime stamp that Pocket reported for this request
    time_since = Column(DateTime)
    # Stats
    nr_added = Column(Integer)
    nr_read = Column(Integer)
    nr_deleted = Column(Integer)
    nr_favourited = Column(Integer)


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


def get_db_connection(get_engine=False):
    """
    Create a SQLAlchemy session
    """
    #engine = create_engine('sqlite:///:memory:', echo=True)
    # Relative path:
    engine = create_engine('sqlite:///pocketstats.db')
    Session = sessionmaker(bind=engine)
    if get_engine:
        return Session(),engine
    else:
        return Session()


def _create_tables():
    session, engine = get_db_connection(get_engine=True)

    inspector = Inspector.from_engine(engine)
    #for table_name in inspector.get_table_names():
    #    print table_name
    if (engine.dialect.has_table(engine.connect(), "Article") == False) or (engine.dialect.has_table(engine.connect(), "Report") == False):
        # TODO: If Article and Report don't exist yet, create:
        Base.metadata.create_all(engine)


def get_last_update():
    """
    Return the timestamp of the last update from Pocket.
    This will be used to filter the request of updates.
    """
    session = get_db_connection()
    for time_since, report_id in session.query(Report.time_since, Report.id):
        print time_since, report_id
    return None


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
    logger = get_logger()
    session = get_db_connection()

    #items = pocket_instance.get(state='unread')
    #print 'Number of items: ' + str(len(items[0]['list']))
    #items = pocket_instance.get(state='archive')
    #print 'Number of items: ' + str(len(items[0]['list']))
    #sys.exit()

    last_time = get_last_update()

    #items = pocket_instance.get()
    pocket_instance = get_pocket_instance()
    items = pocket_instance.get(count=20, state='all')
    #print items[0]['status']
    print 'Number of items: ' + str(len(items[0]['list']))
    logger.debug('Number of items: ' + str(len(items[0]['list'])))

    for item_id in items[0]['list']:
        #print item_id
        item = items[0]['list'][item_id]
        print item
        logger.debug(item)
        #print safe_unicode(item['status']) + ' '+ safe_unicode(item['item_id']) + ' ' + safe_unicode(item['resolved_id']) + ' ' + safe_unicode(item['given_title'])
        print safe_unicode(item['status']) + ' ' + safe_unicode(item['item_id']) + ' ' + safe_unicode(item['resolved_id']) + ' ' + unix_to_string(item['time_added']) + ' ' + unix_to_string(item['time_updated'])
        logger.debug(safe_unicode(item['status']) + ' ' + safe_unicode(item['item_id']) + ' ' + safe_unicode(item['resolved_id']) + ' ' + unix_to_string(item['time_added']) + ' ' + unix_to_string(item['time_updated']))
        #datetime.datetime.fromtimestamp(int(item['time_updated'])).strftime('%Y-%m-%d %H:%M:%S')
        #print safe_unicode(item['given_title'])
        print safe_unicode(item['resolved_url'])
        #print safe_unicode(item['resolved_title'])
        article = Article(sort_id=item['sort_id'], item_id=item['item_id'])
        article.resolved_id = item['resolved_id']
        article.given_url = item['given_url']
        article.resolved_url = item['resolved_url']
        article.given_title = item['given_title']
        article.resolved_title = item['resolved_title']
        article.favorite = item['favorite']
        article.status = item['status']
        article.excerpt = item['excerpt']
        article.is_article = item['is_article']
        article.has_image = item['has_image']
        article.has_video = item['has_video']
        article.word_count = item['word_count']
        #article.tags = item['tags']
        #article.authors = item['authors']
        #article.images = item['images']
        #article.videos = item['videos']
        article.time_updated = datetime.datetime.fromtimestamp(float(item['time_updated']))
        article.time_favorited = datetime.datetime.fromtimestamp(float(item['time_favorited']))
        article.time_read = datetime.datetime.fromtimestamp(float(item['time_read']))
        session.add(article)

    # Check what's pending
    print session.new
    logger.debug('About to commit to DB:')
    logger.debug(session.new)

    # Save to DB
    session.commit()

    #items = pocket_instance.get(state='unread')
    #print items[0]['status']
    #print len(items[0]['list'])


@cli.command()
def createdb():
    """
    Create the database
    """
    _create_tables()


@cli.command()
@click.option('--consumer_key', prompt='Your Consumer Key', help='Get it at https://getpocket.com/developer/')
def gettoken(consumer_key):
    """
    Get access token
    """
    # URL to redirect user to, to authorize your app
    redirect_uri = 'https://github.com/aquatix/pocketstats'
    request_token = Pocket.get_request_token(consumer_key=consumer_key, redirect_uri=redirect_uri)
    auth_url = Pocket.get_auth_url(code=request_token, redirect_uri=redirect_uri)
    print "Open the uri printed below in your browser and allow the application"
    print "Note the key you get in response, as that is your access_token"
    print ""
    print auth_url
    print ""


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
