import logging
import os
import time
import re
from signal import signal, SIGPIPE, SIG_DFL
from subprocess import PIPE, Popen
from threading import Thread
from queue import Queue, Empty

'''
 Currently, for games that require several clicks to get start info, it doesn't
 scrape everything. Lost.z5 is one. The first couple commands will not produce
 the expected output.

 Class Summary: TextPlayer([name of the game file])
 Methods:   run()
            execute_command([command string])
            get_score()
                returns None if no score found
                returns ('2', '100') if 2/100 found
            quit()
'''


class Response:
    location = ""
    description = ""


class textPlayer:

    # Initializes the class, sets variables
    def __init__(self, game_filename):
        signal(SIGPIPE, SIG_DFL)
        self.game_loaded_properly = True

        # Verify that specified game file exists, else limit functionality
        game_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "games",
            game_filename
        )
        if game_filename is None or not os.path.exists(game_path):
            self.game_loaded_properly = False
            raise IOError("Unrecognized game file or bad path", game_filename)
            return

        self.game_filename = game_filename
        self._logger = logging.getLogger(__name__)

    # Runs the game
    def run(self):
        if self.game_loaded_properly:
            # locate dfrotz
            if os.path.isfile(
                os.path.join(
                    os.path.dirname(os.path.realpath(__file__)),
                    "dfrotz"
                )
            ):
                dfrotz = os.path.join(
                    os.path.dirname(os.path.realpath(__file__)),
                    "dfrotz"
                )
            else:
                dfrotz = os.path.join(
                    os.path.dirname(os.path.realpath(__file__)),
                    "dfrotz." + os.uname().machine
                )
            game = os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                "games",
                self.game_filename
            )
            # Start the game process with both 'standard in'
            # and 'standard out' pipes
            self.game_process = Popen(
                [dfrotz, game],
                stdin=PIPE,
                stdout=PIPE,
                bufsize=1,
                universal_newlines=True
            )

            # Create Queue object
            self.output_queue = Queue()
            t = Thread(
                target=self.enqueue_pipe_output,
                args=(self.game_process.stdout, self.output_queue)
            )

            # Thread dies with the program
            t.daemon = True
            t.start()

            # Grab start info from game.
            start_output = self.get_command_output()
            self._logger.info(start_output)
            # The following line matches 'hit' in 'white house' in Zork 1
            # if 'Press' in start_output or 'press' in start_output
            # or 'Hit' in start_output or 'hit' in start_output:
            if 'introduction' in start_output:
                start_output += self.execute_command('no\n')  # Parc
            if(self.game_filename == 'zork1.z5'):
                Response.location = "West of House"
                Response.description = " ".join([
                    "You are standing in an open field west of a white house,",
                    "with a boarded front door. There is a small mailbox here."
                ])
            elif(self.game_filename == 'hhgg.z3'):
                Response.location = "Bedroom"
                Response.description = " ".join([
                    "You wake up. The room is spinning very gently round your",
                    "head. Or at least it would be if you could see it which"
                    "you can't. It is pitch black."
                ])
            return Response
        else:
            raise IOError('Game not loaded properly')

    # Sends buffer from output pipe of game to a queue where it can be
    # retrieved later
    def enqueue_pipe_output(self, output, queue):
        for line in iter(output.readline, ''):
            queue.put(line)
        output.close()

    # Run a bash command and wait until it finishes
    def run_bash(self, command):
        process = Popen(command, shell=True)
        process.wait()

    # Send a command to the game and return the output
    def execute_command(self, command):
        if self.game_loaded_properly:
            self.game_process.stdin.write("".join([command, "\n"]))
            return self.clean_command_output(self.get_command_output())
        else:
            raise IOError('Game not loaded properly')

    # Returns the current score in a game
    def get_score(self):
        if self.game_loaded_properly:
            self.game_process.stdin.write('score\n')
            command_output = self.get_command_output()
            score_pattern = " ".join([
                '[0-9]+',
                '[\(total ]*[points ]*[out ]*of',
                '[a maximum of ]*[a possible ]*[0-9]+'
            ])
            matchObj = re.search(score_pattern, command_output, re.M | re.I)
            if matchObj is not None:
                score_words = matchObj.group().split(' ')
                return(
                    int(score_words[0]),
                    int(score_words[len(score_words)-1])
                )
        return None

    # Remove score and move information from output
    def clean_command_output(self, text):
        response = Response()
        if(
            (
                self.game_filename == 'zork1.z5'
            )or(
                self.game_filename == 'hhgg.z3'
            )
        ):
            matchObj = re.findall(
                '^\s*(.*?)\s*Score:\s*[-]*[0-9]+\s*Moves:\s*[-]*[0-9]+\s*(.*)$',
                text,
                re.I
            )
            if(len(matchObj)):
                response.location = matchObj[0][0]
                response.description = matchObj[0][1]
                # Sometimes the description contains a copy of the location
                # at the beginning. Remove it if so.
                matchObj = re.findall(
                    re.compile(
                        '^\s*'+re.escape(response.location) + '\s*(.*)$',
                        re.I
                    ),
                    response.description
                )
                if(len(matchObj)):
                    response.description = matchObj[0]
            else:
                # otherwise, this was a simple error message from the parser
                # which does not include a score
                response.description = text
        return response

    # Grab the output from the queue
    def get_command_output(self):
        command_output = ''
        output_continues = True
        time.sleep(.2)  # for Hitchhiker's guide to the galaxy

        # While there is still output in the queue
        while(output_continues):
            try:
                line = self.output_queue.get(timeout=.001)
            except Empty:
                output_continues = False
            else:
                command_output += line

        # Clean up the output
        command_output = command_output.replace(
            '\n',
            ' '
        ).replace(
            '>',
            ' '
        ).replace(
            '<',
            ' '
        )
        while '  ' in command_output:
            command_output = command_output.replace('  ', ' ')

        return command_output

    def save(self, filename):
        if self.game_loaded_properly:
            self.game_process.stdin.write('save\n')
            self._logger.info(self.get_command_output())
            self.game_process.stdin.write("".join([filename, '\n']))
            # seems like dfrotz needs a little time to save the game,
            # so the output is not instantly available
            time.sleep(1)
            self._logger.info(self.get_command_output())

    def restore(self, filename):
        if self.game_loaded_properly:
            self.game_process.stdin.write('restore\n')
            self._logger.info(self.get_command_output())
            self.game_process.stdin.write(filename+'\n')
            # seems like it takes a little time to load the game,
            # so the output is not instantly available.
            time.sleep(1)
            self._logger.info(self.get_command_output())

    def quit(self):
        if self.game_loaded_properly:
            self.game_process.stdin.write('quit\n')
            self.game_process.stdin.write('y\n')
        if self.game_process.stdin:
            self.game_process.stdin.write('n\n')
