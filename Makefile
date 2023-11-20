.PHONY: run stop

run:
	tmux new-session -d -s fplonkadevGo 'go build && ./fplonka.dev'

stop:
	tmux send-keys -t fplonkadevGo  'C-c'
	sleep 2
	tmux kill-session -t fplonkadevGo 

