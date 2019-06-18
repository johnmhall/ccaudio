# ccaudio
This project is the code used to automate the processing and posting of sermon audio. The posting of this code is a work-in-progress at this point.

This project is currently in use to populate this site: http://listen.ccgvl.org/

## Project Components
### ccaudio.py
This is the Python code responsible for processing an MP3 file with special tags and adding it into a SQLite database to be used by a web front-end for displaying sermon audio. The following tags (IDv3) are accepted for a given MP3 file:

* ARTIST (required) - This should be the speaker that shared the message.
* TITLE (required) - This should be the title of the message that was shared.
* RELEASE DATE - This should be the date this message was released (in the format 'MM-dd-YYYY' where M is month, d is day, Y is year).
* BOOK - This is the book of the Bible used to share the message.
* CHAPTER - This is the chapter from the BOOK.
* VERSES - This is the set of verses from CHAPTER (in the format of '27' for single or '26-27' for range).

### ccaudio PHP
This is the PHP code responsible for reading the SQLite database populated by ccaudio.py and presenting the user with the following means of obtaining messages:
* Interactively via the HTML renderings
* Automatically via an Apple Podcast generated dynamically
* Automatically via an RSS feed generated dynamically
