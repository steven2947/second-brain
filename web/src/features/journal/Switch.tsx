/** 馆员形象切换（女生/男生）：写入外观偏好并全站同步，不含任何私有数据。 */
import { useCharacter } from './character';

export function CharacterSwitch() {
  const [character, setCharacter] = useCharacter();
  return <div className="character-switch" role="group" aria-label="馆员形象">
    <button type="button" aria-pressed={character === 'girl'} onClick={() => setCharacter('girl')}>女生版</button>
    <button type="button" aria-pressed={character === 'boy'} onClick={() => setCharacter('boy')}>男生版</button>
  </div>;
}
