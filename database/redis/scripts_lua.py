LUA_SET_IF_NEWER = """local key = KEYS[1]

local new_price = ARGV[1]
local new_ts = tonumber(ARGV[2])

local old_ts = redis.call('HGET', key, 'ts_ms')
if old_ts then
  old_ts = tonumber(old_ts)
  if old_ts and old_ts > new_ts then
    return 0
  end
end

redis.call('HSET', key, 'price', new_price, 'ts_ms', tostring(new_ts))
return 1
"""
