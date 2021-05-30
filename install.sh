pip install python-telegram-bot
export PYCURL_SSL_LIBRARY=openssl
export CPPFLAGS=-I/usr/local/opt/openssl/include
export LDFLAGS=-L/usr/local/opt/openssl/lib

pip install pycurl --global-option="--with-openssl"

pip install psycopg2-binary

pip install weasyprint
pip install matplotlib
pip install seaborn
