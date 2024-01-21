host := $(shell hostname)
CFLAGS += -Wall -ggdb -O2 -DHOST=\"$(host)\"
LDLIBS += -lm

TARGET = corsairmi

all: $(TARGET)

clean:
	$(RM) $(TARGET)

.PHONY: all clean
