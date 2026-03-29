# agentctl

`agentctl` is the supported operator-facing command for agent runtime control.

Today it still delegates directly to the underlying toolkit gateway wrapper, but operators should treat `agentctl` as the canonical surface.
Use it when you want a control surface that matches other toolkit commands such as `modelctl`.

## Usage

```bash
~/bin/agentctl [start|stop|restart|status|logs|setup] [openclaw|hermes|all]
```

## Notes

- `agentctl` is currently implemented as a thin wrapper over the underlying gateway runtime script.
- `gateway` is deprecated and scheduled for removal.
- Backend behavior, config precedence, and status output are identical during the transition.
